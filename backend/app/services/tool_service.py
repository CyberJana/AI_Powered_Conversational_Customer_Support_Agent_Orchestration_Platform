"""Tool execution engine (FR-12): a fixed, explicitly allow-listed set of
tools, each with a name, description, JSON input schema, permission, and
timeout, invoked with audit logging via `ToolCall` rows. No arbitrary
code/SQL execution from the LLM is permitted - only these hard-coded
handlers, each doing a real (seeded) database read/write.
"""
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.models.agent import Tool, ToolCall
from app.models.commerce import Order, Product
from app.models.evaluation import Escalation

REFUND_ELIGIBLE_STATUSES = {"shipped", "delivered"}
REFUND_WINDOW_DAYS = 30


class ToolExecutionError(RuntimeError):
    """Raised when a tool's input is invalid or its handler fails."""


class ToolContext:
    def __init__(self, organization_id: uuid.UUID, conversation_id: uuid.UUID):
        self.organization_id = organization_id
        self.conversation_id = conversation_id


def _require_fields(input_data: dict, schema: dict) -> None:
    missing = [f for f in schema.get("required", []) if f not in input_data or input_data[f] in (None, "")]
    if missing:
        raise ToolExecutionError(f"Missing required field(s): {missing}")


def _handle_get_order(db: Session, ctx: ToolContext, input_data: dict) -> dict:
    order = (
        db.query(Order)
        .filter(Order.organization_id == ctx.organization_id, Order.order_number == input_data["order_id"])
        .first()
    )
    if order is None:
        raise ToolExecutionError(f"No order found with id '{input_data['order_id']}'")
    return {
        "order_id": order.order_number,
        "status": order.status,
        "total_amount": order.total_amount,
        "placed_at": order.placed_at.isoformat(),
        "items": order.items,
    }


def _handle_search_product(db: Session, ctx: ToolContext, input_data: dict) -> dict:
    query = input_data["query"]
    limit = int(input_data.get("limit") or 5)
    results = (
        db.query(Product)
        .filter(Product.organization_id == ctx.organization_id, Product.name.ilike(f"%{query}%"))
        .limit(limit)
        .all()
    )
    return {
        "results": [
            {"product_id": p.sku, "name": p.name, "price": p.price, "in_stock": p.stock_quantity > 0}
            for p in results
        ]
    }


def _handle_get_product(db: Session, ctx: ToolContext, input_data: dict) -> dict:
    product = (
        db.query(Product)
        .filter(Product.organization_id == ctx.organization_id, Product.sku == input_data["product_id"])
        .first()
    )
    if product is None:
        raise ToolExecutionError(f"No product found with id '{input_data['product_id']}'")
    return {
        "product_id": product.sku,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "stock_quantity": product.stock_quantity,
    }


def _handle_check_refund_policy(db: Session, ctx: ToolContext, input_data: dict) -> dict:
    order = (
        db.query(Order)
        .filter(Order.organization_id == ctx.organization_id, Order.order_number == input_data["order_id"])
        .first()
    )
    if order is None:
        raise ToolExecutionError(f"No order found with id '{input_data['order_id']}'")

    if order.status not in REFUND_ELIGIBLE_STATUSES:
        return {"eligible": False, "reason": f"Orders with status '{order.status}' are not refund-eligible."}

    placed_at = order.placed_at
    if placed_at.tzinfo is None:
        placed_at = placed_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - placed_at
    if age > timedelta(days=REFUND_WINDOW_DAYS):
        return {"eligible": False, "reason": f"Order was placed more than {REFUND_WINDOW_DAYS} days ago."}

    return {"eligible": True, "reason": "Order qualifies for a refund."}


def _handle_create_support_ticket(db: Session, ctx: ToolContext, input_data: dict) -> dict:
    escalation = Escalation(
        conversation_id=ctx.conversation_id,
        reason=f"[{input_data.get('priority', 'medium')}] {input_data['subject']}: {input_data['description']}",
        status="open",
    )
    db.add(escalation)
    db.flush()
    return {"ticket_id": str(escalation.id), "status": escalation.status}


#: Maps a Tool.name to its handler. This is the *only* way tool names can
#: execute code - there is no dynamic/eval-based dispatch.
TOOL_HANDLERS: dict[str, Callable[[Session, ToolContext, dict], dict]] = {
    "get_order": _handle_get_order,
    "search_product": _handle_search_product,
    "get_product": _handle_get_product,
    "check_refund_policy": _handle_check_refund_policy,
    "create_support_ticket": _handle_create_support_ticket,
}


def execute_tool(
    db: Session,
    agent_run_id: uuid.UUID,
    tool_name: str,
    input_data: dict,
    ctx: ToolContext,
) -> ToolCall:
    """Validates, executes, times, and audit-logs a single tool call. Always
    returns a persisted ToolCall (success or failure) rather than raising,
    so a failed tool call is itself part of the conversation's audit trail.
    """
    tool = db.query(Tool).filter(Tool.name == tool_name, Tool.enabled.is_(True)).first()
    handler = TOOL_HANDLERS.get(tool_name)

    start = time.monotonic()
    output: dict | None = None
    success = False
    error_message: str | None = None

    if tool is None or handler is None:
        error_message = f"Tool '{tool_name}' is not an enabled, allow-listed tool."
    else:
        try:
            _require_fields(input_data, tool.input_schema or {})
            output = handler(db, ctx, input_data)
            success = True
        except ToolExecutionError as exc:
            error_message = str(exc)
        except Exception as exc:  # noqa: BLE001 - any handler failure is recorded, not raised
            error_message = f"Tool execution failed: {exc}"

    duration_ms = int((time.monotonic() - start) * 1000)

    tool_call = ToolCall(
        agent_run_id=agent_run_id,
        tool_id=tool.id if tool else None,
        tool_name=tool_name,
        input=input_data,
        output=output,
        success=success,
        duration_ms=duration_ms,
        error_message=error_message,
    )
    db.add(tool_call)
    db.flush()
    return tool_call
