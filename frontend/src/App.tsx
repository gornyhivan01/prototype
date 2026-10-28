import { Navigate, Route, Routes } from "react-router-dom";

import { Dashboard } from "./pages/Dashboard";
import { Landing } from "./pages/Landing";

export function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
