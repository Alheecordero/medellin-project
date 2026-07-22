import Topbar from "@/components/Topbar";
import Footer from "@/components/Footer";
import type { Locale } from "@/lib/types";
import type { ReactNode } from "react";

export default function SiteShell({
  locale,
  children,
}: {
  locale: Locale;
  children: ReactNode;
}) {
  return (
    <>
      <Topbar locale={locale} />
      <main>{children}</main>
      <Footer locale={locale} />
    </>
  );
}
