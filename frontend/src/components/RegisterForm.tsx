import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";

export function RegisterForm() {
  const { register, isLoading } = useAuthStore();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget));
    if (form.password !== form.confirm) {
      setError("Passwords must match.");
      return;
    }
    try {
      await register({
        email: String(form.email),
        password: String(form.password),
        full_name: String(form.full_name),
      });
      navigate("/login");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Registration failed.");
    }
  }
  return (
    <main className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <section className="w-full max-w-md bg-white shadow-xl rounded-lg p-8">
        <h1 className="text-3xl font-bold mb-3">Create your account</h1>
        <p className="text-gray-600 mb-6">
          Register with the connected InvoiceFlow service.
        </p>
        <form onSubmit={submit} className="space-y-4">
          <label className="block">
            Name
            <input
              name="full_name"
              maxLength={100}
              className="block border rounded p-2 w-full"
            />
          </label>
          <label className="block">
            Email
            <input
              name="email"
              type="email"
              required
              maxLength={200}
              className="block border rounded p-2 w-full"
              autoComplete="email"
            />
          </label>
          <label className="block">
            Password
            <input
              name="password"
              type="password"
              minLength={12}
              maxLength={128}
              required
              className="block border rounded p-2 w-full"
              autoComplete="new-password"
            />
          </label>
          <label className="block">
            Confirm password
            <input
              name="confirm"
              type="password"
              required
              className="block border rounded p-2 w-full"
              autoComplete="new-password"
            />
          </label>
          {error && (
            <p role="alert" className="text-red-700">
              {error}
            </p>
          )}
          <button
            disabled={isLoading}
            className="bg-blue-600 text-white rounded px-4 py-3 w-full disabled:opacity-50"
          >
            {isLoading ? "Creating account…" : "Create account"}
          </button>
        </form>
        <Link to="/login" className="block mt-6 text-blue-600">
          Back to sign in
        </Link>
      </section>
    </main>
  );
}
