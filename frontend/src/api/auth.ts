import { api } from "./client";

export interface LoginResponse {
  access_token: string; token_type: string; roles: string[]; nombre: string;
}
export interface MeResponse {
  id: number; email: string; nombre: string; roles: string[];
}

export const authApi = {
  login: (email: string, password: string) =>
    api.post<LoginResponse>("/auth/login", { email, password }),
  me: () => api.get<MeResponse>("/auth/me"),
};