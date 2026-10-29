import { redirect } from "next/navigation";

export default function Home() {
  redirect("/dashboard"); // middleware sends anonymous visitors on to /login
}
