import { api } from 'src/boot/api';

export interface Category {
  id: string;
  name: string;
  description: string | null;
  default_tax_rate_id: string | null;
}

interface CategoriesResponse {
  data: Category[];
  count: number;
}

export async function listCategories(): Promise<Category[]> {
  const { data } = await api.get<CategoriesResponse>('/category/', {
    params: { limit: 500 },
  });
  return data.data;
}
