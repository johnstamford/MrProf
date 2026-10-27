import type { ReactNode } from "react";
import AssessmentHeader from "../components/AssessmentHeader";

export const metadata = { title: "MrProf" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: "2rem" }}>
        <AssessmentHeader />
        {children}
      </body>
    </html>
  );
}
