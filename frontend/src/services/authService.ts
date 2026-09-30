import { apiClient } from "./apiClient";
import type { AuthUser, LoginPayload, SignupPayload, TokenPair } from "@/types/auth";

export const authService = {
  signup: async (payload: SignupPayload) => {
    const { data } = await apiClient.post<TokenPair & AuthUser>("/auth/signup", payload);
    return data;
  },
  login: async (payload: LoginPayload) => {
    const { data } = await apiClient.post<TokenPair>("/auth/login", payload);
    return data;
  },
  me: async () => {
    const { data } = await apiClient.get<AuthUser>("/auth/me");
    return data;
  },
};
