import type { Metadata } from "next";
import { Fraunces, Mrs_Saint_Delafield, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Navbar } from "@/components/layout/Navbar";
import { ToastContainer } from "@/components/layout/ToastContainer";

const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-fraunces",
  axes: ["SOFT", "WONK", "opsz"],
  style: ["normal", "italic"],
  display: "swap",
});

// Cursive — reserved for the small wordmark in the shell only.
const mrsSaintDelafield = Mrs_Saint_Delafield({
  subsets: ["latin"],
  variable: "--font-script",
  weight: "400",
  display: "swap",
});

// Mono — used heavily for IDs, durations, scores, stage names.
const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono-face",
  display: "swap",
});

export const metadata: Metadata = {
  title: "YT Shorts Engineer",
  description: "A workspace for turning long-form video into short clips.",
  keywords: ["youtube shorts", "video editing", "clip generator", "LangGraph"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${fraunces.variable} ${mrsSaintDelafield.variable} ${geistMono.variable}`}
    >
      <body className="font-sans antialiased min-h-screen">
        <Providers>
          <div className="flex flex-col min-h-screen">
            <Navbar />
            <main className="flex-1 w-full max-w-[1280px] mx-auto px-4 sm:px-6 py-6">
              {children}
            </main>
          </div>
          <ToastContainer />
        </Providers>
      </body>
    </html>
  );
}
