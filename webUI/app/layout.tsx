import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Nora",
  description: "Nora, Dr. Shalini's clinic assistant for actions, schedules, patients, and approval records.",
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
