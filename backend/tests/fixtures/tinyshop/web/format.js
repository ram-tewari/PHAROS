/** Render a decimal string as a localized currency amount, e.g. "$12.50". */
function formatPrice(amount, currency = "USD") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(Number(amount));
}

module.exports = { formatPrice };
