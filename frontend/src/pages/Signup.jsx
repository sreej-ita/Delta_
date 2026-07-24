import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Sprout, UserPlus } from "lucide-react";
import { useAuth } from "../lib/auth.jsx";

export default function Signup() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    if (password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    setBusy(true);
    try {
      await signup(name, email, password);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message || "Signup failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div
        className="pointer-events-none absolute left-1/2 top-1/4 h-72 w-[520px] -translate-x-1/2 rounded-full opacity-20 blur-3xl"
        style={{ background: "radial-gradient(circle, #3b82f6, transparent 70%)" }}
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

        <h1 className="font-display text-xl font-bold text-ink">Create account</h1>
        <p className="mt-1 text-sm text-muted">Set up access to your mangrove monitoring sites.</p>

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label className="mb-1.5 block text-xs uppercase tracking-wide text-muted">Full name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Jane Doe"
              className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-ink outline-none placeholder:text-slate-600 focus:border-emerald"
            />
          </div>
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
              placeholder="At least 6 characters"
              className="w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-ink outline-none placeholder:text-slate-600 focus:border-emerald"
            />
          </div>

          {error && <p className="text-sm text-rose">{error}</p>}

          <button
            type="submit"
            disabled={busy}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-emerald to-blue py-2.5 text-sm font-semibold text-white transition-transform hover:scale-[1.01] disabled:opacity-60"
          >
            <UserPlus size={16} />
            {busy ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-muted">
          Already have an account?{" "}
          <Link to="/login" className="font-medium text-emerald hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
