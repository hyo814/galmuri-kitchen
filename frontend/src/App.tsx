import { useEffect, useState } from "react";
import { api, type User } from "./api";
import Fridge from "./pages/Fridge";
import Login from "./pages/Login";

export default function App() {
  // undefined: 확인 중, null: 비로그인
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    api<User>("/api/me").then(setUser, () => setUser(null));
  }, []);

  if (user === undefined) return <p className="center muted">불러오는 중…</p>;
  if (user === null) return <Login onLogin={setUser} />;
  return <Fridge onLogout={() => setUser(null)} />;
}
