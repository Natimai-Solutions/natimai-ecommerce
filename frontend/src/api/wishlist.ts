import { api } from '@/boot/api';

/** Un article de la liste de favoris (`WishlistItemDetail`). */
export interface WishlistItem {
  id: string;
  product_id: string;
  notes: string | null;
  created_at: string | null;
}

export interface Wishlist {
  id: string;
  name: string;
  items: WishlistItem[];
}

export async function getMyWishlist(): Promise<Wishlist> {
  const { data } = await api.get<Wishlist>('/wishlist/me');
  return data;
}

export async function addToMyWishlist(productId: string): Promise<Wishlist> {
  const { data } = await api.post<Wishlist>('/wishlist/me/items', { product_id: productId });
  return data;
}

export async function removeFromMyWishlist(productId: string): Promise<Wishlist> {
  const { data } = await api.delete<Wishlist>(`/wishlist/me/items/${productId}`);
  return data;
}
