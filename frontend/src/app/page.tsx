import Topbar from "@/components/Topbar";
import Footer from "@/components/Footer";
import HomePage from "@/components/HomePage";
import { getHome } from "@/lib/api";

export const revalidate = 60;

export default async function Page() {
  const data = await getHome("es");

  return (
    <>
      <Topbar locale="es" />
      <main>
        <HomePage data={data} locale="es" />
      </main>
      <Footer locale="es" />
    </>
  );
}
