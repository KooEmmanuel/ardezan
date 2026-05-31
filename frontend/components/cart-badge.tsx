"use client";

import { useEffect, useState } from "react";

import { CART_EVENT, readCart } from "@/lib/cart";

export function CartBadge() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const sync = () => setCount(readCart().reduce((sum, line) => sum + line.quantity, 0));
    sync();
    window.addEventListener(CART_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(CART_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  if (count <= 0) return null;
  return (
    <span
      aria-label={`${count} items in cart`}
      className="absolute -top-1 -right-1 bg-[color:var(--ink)] text-[color:var(--paper)] text-[10px] rounded-full w-4 h-4 flex items-center justify-center"
    >
      {count}
    </span>
  );
}
