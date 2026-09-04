"use client";

import { useEffect, useState, type FormEvent } from "react";
import type { Product } from "@agentic-merchant/shared-types";
import { apiGet, apiPost, apiDelete, ApiError } from "../../lib/api";
import { useMerchant } from "../../lib/merchant-context";

type ProductCreatePayload = Omit<Product, "id">;

interface FormState {
  name: string;
  description: string;
  price: string;
  currency: string;
  category: string;
  tags: string;
  stock: string;
}

const initialForm: FormState = {
  name: "",
  description: "",
  price: "",
  currency: "INR",
  category: "",
  tags: "",
  stock: "0",
};

export default function CatalogPage() {
  const { merchantId } = useMerchant();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(initialForm);
  const [submitting, setSubmitting] = useState(false);

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function loadProducts(id: string, isCancelled: () => boolean = () => false) {
    setLoading(true);
    setError(null);
    try {
      const data = await apiGet<Product[]>(`/merchant/products?merchant_id=${id}`);
      if (!isCancelled()) setProducts(data);
    } catch (err) {
      if (!isCancelled()) setError(err instanceof ApiError ? err.message : "Failed to load products.");
    } finally {
      if (!isCancelled()) setLoading(false);
    }
  }

  useEffect(() => {
    if (!merchantId) {
      setProducts([]);
      return;
    }

    // Guard against out-of-order responses: switching merchants fires a new
    // fetch before the previous one necessarily resolves, and without this a
    // slower, stale response can overwrite fresher state.
    let cancelled = false;
    loadProducts(merchantId, () => cancelled);

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [merchantId]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!merchantId) return;
    setError(null);
    setSubmitting(true);

    const payload: ProductCreatePayload = {
      merchantId,
      name: form.name,
      description: form.description || null,
      price: Number(form.price),
      currency: form.currency,
      category: form.category || null,
      tags: form.tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      stock: Number(form.stock) || 0,
    };

    try {
      await apiPost<Product>("/merchant/products", payload);
      setForm(initialForm);
      await loadProducts(merchantId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create product.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(productId: string) {
    if (!merchantId) return;
    setError(null);
    try {
      await apiDelete(`/merchant/products/${productId}`);
      await loadProducts(merchantId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete product.");
    }
  }

  if (!merchantId) {
    return (
      <main className="container">
        <header className="page-header">
          <h1>Catalog</h1>
        </header>
        <div className="banner banner-warning">
          No merchant selected. Go to <a href="/onboarding">Onboarding</a> first.
        </div>
      </main>
    );
  }

  return (
    <main className="container">
      <header className="page-header">
        <h1>Catalog</h1>
        <p className="page-subtitle">
          Products your policy and agents can see. Changes take effect immediately — this is the
          exact list <code>GET /agent/catalog</code> returns.
        </p>
      </header>

      {error && <div className="banner banner-error">{error}</div>}

      <form className="card" onSubmit={handleSubmit}>
        <h2>Add product</h2>
        <div className="form-row">
          <div className="field">
            <label htmlFor="name">Name</label>
            <input
              id="name"
              required
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="category">Category</label>
            <input
              id="category"
              value={form.category}
              onChange={(e) => update("category", e.target.value)}
            />
          </div>
        </div>

        <div className="field">
          <label htmlFor="description">Description</label>
          <input
            id="description"
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
          />
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="price">Price</label>
            <input
              id="price"
              type="number"
              min="0"
              step="0.01"
              required
              value={form.price}
              onChange={(e) => update("price", e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="currency">Currency</label>
            <input
              id="currency"
              value={form.currency}
              onChange={(e) => update("currency", e.target.value)}
            />
          </div>
        </div>

        <div className="form-row">
          <div className="field">
            <label htmlFor="tags">Tags</label>
            <input
              id="tags"
              placeholder="new, featured"
              value={form.tags}
              onChange={(e) => update("tags", e.target.value)}
            />
            <span className="hint">Comma-separated.</span>
          </div>
          <div className="field">
            <label htmlFor="stock">Stock</label>
            <input
              id="stock"
              type="number"
              min="0"
              value={form.stock}
              onChange={(e) => update("stock", e.target.value)}
            />
          </div>
        </div>

        <button className="btn" type="submit" disabled={submitting}>
          {submitting ? "Adding…" : "Add product"}
        </button>
      </form>

      <div className="card">
        <h2>Products</h2>
        {loading ? (
          <div className="skeleton-row">
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        ) : products.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📦</div>
            <p>No products yet — add the first one above.</p>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Category</th>
                <th>Price</th>
                <th>Stock</th>
                <th>Tags</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => (
                <tr key={p.id}>
                  <td><strong>{p.name}</strong></td>
                  <td>{p.category ?? <span className="muted">—</span>}</td>
                  <td>
                    {p.price} {p.currency}
                  </td>
                  <td>{p.stock}</td>
                  <td>{p.tags.join(", ") || <span className="muted">—</span>}</td>
                  <td>
                    <button className="btn-danger" onClick={() => handleDelete(p.id)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </main>
  );
}
