import { api } from 'src/boot/api';

export interface Place {
  id: string;
  name: string;
  type: string;
  code: string | null;
  country: string | null;
  city: string | null;
  is_warehouse: boolean;
  customs_clearance: boolean;
}

export interface PlaceCreate {
  name: string;
  type: string;
  code?: string | null;
  country?: string | null;
  city?: string | null;
  is_warehouse?: boolean;
  customs_clearance?: boolean;
}

export interface ShippingRoute {
  id: string;
  name: string;
  from_place_id: string;
  to_place_id: string;
  mode: string;
  service_level: string | null;
  customer_label: string | null;
  eta_days: number | null;
  price_per_kg: string | null;
  base_price: string | null;
  is_to_customer: boolean;
  last_leg_delivery_type: string | null;
  status_code: string | null;
}

export interface ShippingRouteCreate {
  name: string;
  from_place_id: string;
  to_place_id: string;
  mode: string;
  service_level?: string | null;
  customer_label?: string | null;
  eta_days?: number | null;
  price_per_kg?: string | null;
  base_price?: string | null;
  is_to_customer?: boolean;
  last_leg_delivery_type?: string | null;
}

interface Paginated<T> {
  data: T[];
  count: number;
}

// --- Places --------------------------------------------------------------- //
export async function listPlaces(): Promise<Place[]> {
  const { data } = await api.get<Paginated<Place>>('/place', { params: { limit: 500 } });
  return data.data;
}

export async function createPlace(payload: PlaceCreate): Promise<Place> {
  const { data } = await api.post<Place>('/place', payload);
  return data;
}

export async function updatePlace(id: string, payload: Partial<PlaceCreate>): Promise<Place> {
  const { data } = await api.put<Place>(`/place/${id}`, payload);
  return data;
}

// --- Routes (tronçons) ---------------------------------------------------- //
export async function listRoutes(): Promise<ShippingRoute[]> {
  const { data } = await api.get<Paginated<ShippingRoute>>('/shipping/route', {
    params: { limit: 500 },
  });
  return data.data;
}

export async function createRoute(payload: ShippingRouteCreate): Promise<ShippingRoute> {
  const { data } = await api.post<ShippingRoute>('/shipping/route', payload);
  return data;
}

export async function updateRoute(
  id: string,
  payload: Partial<ShippingRouteCreate>,
): Promise<ShippingRoute> {
  const { data } = await api.put<ShippingRoute>(`/shipping/route/${id}`, payload);
  return data;
}
