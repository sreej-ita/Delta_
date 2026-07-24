import { createContext, useContext, useEffect, useState } from "react";
import { api } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("bcm_token");
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then((u) => setUser(u))
      .catch(() => localStorage.removeItem("bcm_token"))
      .finally(() => setLoading(false));
  }, []);

  async function login(email, password) {
    const data = await api.login(email, password);
    localStorage.setItem("bcm_token", data.access_token);
    setUser({ name: data.name, email: data.email });
  }

  async function signup(name, email, password) {
    const data = await api.signup(name, email, password);
    localStorage.setItem("bcm_token", data.access_token);
    setUser({ name: data.name, email: data.email });
  }

  function logout() {
    localStorage.removeItem("bcm_token");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
