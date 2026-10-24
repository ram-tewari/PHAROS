/** An authenticated user session as returned by POST /login. */
export interface Session {
  token: string;
  username: string;
}

/** One product line in the cart. */
export interface CartLine {
  sku: string;
  price: string;
  quantity: number;
}
