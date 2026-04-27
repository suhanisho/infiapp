import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "Infiloop",
  description: "Minimal web app built with the Infiloop framework.",
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

