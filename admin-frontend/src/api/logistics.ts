import { api } from 'src/boot/api';

export interface Place {
  id: string;
  name: string;
  type: string;
  code: string | null;
  country: string | null;
  city: string | null;
  parent_id: string | null;
  is_warehouse: boolean;
  /** The one warehouse supplier goods converge to (set via setMainWarehouse). */
  is_main_warehouse: boolean;
  customs_clearance: boolean;
  /** Supplier origin: 'domestic' | 'import' override, null = by country. */
  customs_regime: string | null;
  /** Supplier ships straight to the customer (dropshipping). */
  dropship_enabled: boolean;
}

export interface PlaceCreate {
  name: string;
  type: string;
  code?: string | null;
  country?: string | null;
  city?: string | null;
  parent_id?: string | null;
  is_warehouse?: boolean;
  customs_clearance?: boolean;
  customs_regime?: string | null;
  dropship_enabled?: boolean;
}

/** One row of a carrier's weight grid: `price` up to `max_kg` (null = and above). */
export interface WeightBand {
  max_kg: string | null;
  price: string;
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
  weight_bands: WeightBand[] | null;
  free_shipping_threshold: string | null;
  is_to_customer: boolean;
  last_leg_delivery_type: string | null;
  always_available: boolean;
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
  weight_bands?: WeightBand[] | null;
  free_shipping_threshold?: string | null;
  is_to_customer?: boolean;
  last_leg_delivery_type?: string | null;
  always_available?: boolean;
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

/** Flag `id` as the single main warehouse (the previous one is unflagged). */
export async function setMainWarehouse(id: string): Promise<Place> {
  const { data } = await api.post<Place>(`/place/${id}/set-main-warehouse`);
  return data;
}

// Codes postaux rattachés à une zone (déduction île/commune à l'adresse).
export async function getPlacePostalCodes(id: string): Promise<string[]> {
  const { data } = await api.get<string[]>(`/place/${id}/postal-codes`);
  return data;
}

export async function setPlacePostalCodes(
  id: string,
  country: string,
  postalCodes: string[],
): Promise<string[]> {
  const { data } = await api.put<string[]>(`/place/${id}/postal-codes`, {
    country,
    postal_codes: postalCodes,
  });
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

// Zones desservies par un trajet (une zone parente couvre ses enfants).
interface ServedPlacesResponse {
  route_id: string;
  places: Place[];
}

export async function getRouteServedPlaces(routeId: string): Promise<Place[]> {
  const { data } = await api.get<ServedPlacesResponse>(`/shipping/route/${routeId}/served-places`);
  return data.places;
}

export async function setRouteServedPlaces(routeId: string, placeIds: string[]): Promise<Place[]> {
  const { data } = await api.put<ServedPlacesResponse>(`/shipping/route/${routeId}/served-places`, {
    place_ids: placeIds,
  });
  return data.places;
}
