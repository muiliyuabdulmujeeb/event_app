import { PropsWithChildren } from "react";

type PageContainerProps = PropsWithChildren<{
  narrow?: boolean;
}>;

export function PageContainer({ children, narrow = false }: PageContainerProps) {
  return <section className={narrow ? "page-container page-container--narrow" : "page-container"}>{children}</section>;
}
