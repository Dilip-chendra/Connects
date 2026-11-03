import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Connects — AI-Powered Startup Operating System',
  description: 'One Goal. Connected Tools. Real Outcomes.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-slate-100 antialiased selection:bg-brand-cyan/20 selection:text-brand-cyan">
        {children}
      </body>
    </html>
  );
}
