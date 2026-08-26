/** Layout raíz que exige el App Router; el HTML vive en app/[locale]/layout.tsx. */
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return children;
}
