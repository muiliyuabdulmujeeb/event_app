import { PageHeader } from "../components/PageHeader";

type PlaceholderPageProps = {
  title: string;
  description: string;
  eyebrow?: string;
};

export function PlaceholderPage({ title, description, eyebrow }: PlaceholderPageProps) {
  return (
    <section className="panel">
      <PageHeader eyebrow={eyebrow} title={title} description={description} />
    </section>
  );
}
