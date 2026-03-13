import type { Metadata } from "next";
import { AboutRouteHandler } from "@/app/about/about-route-handler";

export const metadata: Metadata = {
  title: "About Us",
  description:
    "Know the developer behind ScanMyBill, the AI billing platform specially made for Indian MSMEs.",
};

export default function AboutPage() {
  return <AboutRouteHandler />;
}



