import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";
import { Loading } from "../components/Loading";

export function RequireAuth({ children }: { children: JSX.Element }) {
  const { ready, email } = useAuth();
  const loc = useLocation();
  if (!ready) return <Loading />;
  if (!email) return <Navigate to="/login" state={{ from: loc }} replace />;
  return children;
}