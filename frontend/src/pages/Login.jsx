import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Sprout, LogIn } from "lucide-react";
import { useAuth } from "../lib/auth.jsx";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message || "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div
        className="pointer-events-none absolute left-1/2 top-1/4 h-72 w-[520px] -translate-x-1/2 rounded-full opacity-20 blur-3xl"
        style={{ background: "radial-gradient(circle, #10b981, transparent 70%)" }}
      />
      <div className="glass-card relative w-full max-w-sm p-8">
        <div className="mb-6 flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-emerald/15 text-emerald">
            <Sprout size={20} />
          </span>
          <div>
            <p className="font-display text-sm font-semibold text-ink">Blue Carbon Monitor</p>
            <p className="text-xs text-muted">Ecosystem MRV Portal</p>
          </div>
        </div>

        <h1 className="font-display text-xl font-bold text-ink">Sign in</h1>
        <p className="mt-1 text-sm text-muted">Access live satellite monitoring for your project sites.</p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label className="mb-1.5 block text-xs uppercase tracking-wide text-muted">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@organization.org"
              className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-ink outline-none placeholder:text-slate-600 focus:border-emerald"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs uppercase tracking-wide text-muted">Password</label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-ink outline-none placeholder:text-slate-600 focus:border-emerald"
            />
          </div>

          {error && <p className="text-sm text-rose">{error}</p>}

          <button
            type="submit"
            disabled={busy}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-emerald to-blue py-2.5 text-sm font-semibold text-white transition-transform hover:scale-[1.01] disabled:opacity-60"
          >
            <LogIn size={16} />
            {busy ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-muted">
          No account yet?{" "}
          <Link to="/signup" className="font-medium text-emerald hover:underline">
            Create one
          </Link>
        </p>
      </div>
    </div>
  );
}
