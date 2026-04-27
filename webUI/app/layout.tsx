import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Infiapp",
  description: "Minimal web app built with the Infiapp framework.",
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
