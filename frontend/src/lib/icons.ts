import {
  Accessibility,
  Bike,
  Cake,
  Camera,
  Coffee,
  CreditCard,
  CupSoda,
  Ellipsis,
  Heart,
  House,
  Martini,
  Music,
  ShoppingBag,
  Smile,
  Sparkles,
  Store,
  TreePine,
  Users,
  Utensils,
  Wine,
  type LucideIcon,
} from "lucide-react";

/**
 * La API devuelve clases de Bootstrap Icons (categorias_reales y
 * etiquetas_especiales en explorer/views.py). Aquí se traducen a lucide.
 */
const BI_TO_LUCIDE: Record<string, LucideIcon> = {
  "bi-cup-hot": Utensils,
  "bi-cup-straw": Martini,
  "bi-cup": Coffee,
  "bi-camera": Camera,
  "bi-three-dots": Ellipsis,
  "bi-bicycle": Bike,
  "bi-bag": ShoppingBag,
  "bi-house": House,
  "bi-tree": TreePine,
  "bi-music-note-beamed": Music,
  "bi-people": Users,
  "bi-emoji-smile": Smile,
  "bi-cake": Cake,
  "bi-universal-access": Accessibility,
  "bi-heart": Heart,
  "bi-credit-card": CreditCard,
  "bi-stars": Sparkles,
  "bi-glass": Wine,
  "bi-soda": CupSoda,
};

export function iconFor(biClass: string | null | undefined): LucideIcon {
  if (!biClass) return Store;
  return BI_TO_LUCIDE[biClass] ?? Store;
}
