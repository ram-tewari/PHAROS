// Browser client for the tinyshop API.
const { formatPrice } = require("./format");

const API_BASE = "/api";

/**
 * Log in and remember the session token in localStorage.
 */
async function login(username, password) {
  const res = await fetch(`${API_BASE}/login`, {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error("login failed");
  const { token } = await res.json();
  localStorage.setItem("token", token);
  return token;
}

/** Add a product to the cart and return the formatted new total. */
async function addToCart(sku, price, quantity = 1) {
  const res = await fetch(`${API_BASE}/cart/items`, {
    method: "POST",
    headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
    body: JSON.stringify({ sku, price, quantity }),
  });
  const { total } = await res.json();
  return formatPrice(total);
}

module.exports = { login, addToCart };
