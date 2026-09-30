export type UserRole = "admin" | "agent" | "customer";

export interface AuthUser {
  id: string;
  email: string;
  full_name?: string;
  role: UserRole;
  organization_id?: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface SignupPayload {
  email: string;
  password: string;
  full_name: string;
  role?: UserRole;
}

export interface LoginPayload {
  email: string;
  password: string;
}
