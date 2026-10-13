import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { LiveProvider } from "./lib/live";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import CompanyDetail from "./pages/CompanyDetail";
import Comparison from "./pages/Comparison";
import Admin from "./pages/Admin";
import Layout from "./components/Layout";

export default function App() {
  const { role } = useAuth();

  if (!role) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <LiveProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/company/:id" element={<CompanyDetail />} />
          <Route path="/compare" element={<Comparison />} />
          <Route
            path="/admin"
            element={role === "admin" ? <Admin /> : <Navigate to="/dashboard" replace />}
          />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Layout>
    </LiveProvider>
  );
}