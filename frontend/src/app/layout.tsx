import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";
import { ClerkProvider, SignInButton, SignUpButton, Show, UserButton } from "@clerk/nextjs";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: "Market Intelligence PaaS",
  description: "Autonomous Market Mapping",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={cn("font-sans", inter.variable)}>
      <body className="antialiased font-sans bg-slate-50 text-slate-900">
        <ClerkProvider>
          <header className="flex justify-end p-4 bg-white border-b border-slate-200">
            <Show when="signed-out">
              <div className="flex gap-4">
                <SignInButton />
                <SignUpButton />
              </div>
            </Show>
            <Show when="signed-in">
              <UserButton />
            </Show>
          </header>
          {children}
        </ClerkProvider>
      </body>
    </html>
  );
}
