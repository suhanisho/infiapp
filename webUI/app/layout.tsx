import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Dr. Shalini's Clinic",
  description: "Clinic assistant for actions, schedule, patients, and approval records.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
