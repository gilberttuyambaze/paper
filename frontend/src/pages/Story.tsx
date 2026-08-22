import { Link } from 'react-router-dom';
import BrandMark from '@/components/BrandMark';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Lightbulb, ShieldCheck, Search, Users, ExternalLink } from 'lucide-react';

const pillars = [
  {
    title: 'The problem we saw',
    description:
      'UR students often depend on scattered class groups and informal sharing to find past papers, assignments, and worked solutions. Valuable material disappears, quality is uneven, and preparation becomes harder than it should be.',
  },
  {
    title: 'The system we wanted',
    description:
      'A structured academic hub where content is organized by college, department, course, and year, while still keeping the energy of a student community through uploads, discussion, and shared solutions.',
  },
  {
    title: 'The promise we care about',
    description:
      'Reliable access, better revision, and a digital academic archive that can serve both current students and future generations at the University of Rwanda.',
  },
];

const features = [
  'Centralized repository of past papers and solutions',
  'Role-based moderation with admin, content manager, CP, lecturer, and contributor paths',
  'Verification layers for official, community-trusted, and unverified content',
  'Discussion and collaborative learning around each paper',
  'Fast search by course code, name, lecturer, year, and type',
  'Mobile-first access with progressive enhancement and offline support',
];

const studyTips = [
  {
    title: 'Start with the newest relevant paper',
    description:
      'Use the most recent exam or CAT you can find for your course code, then move backward to older papers. This reveals what has stayed consistent and what changes with different lecturers or teaching periods.',
  },
  {
    title: 'Revise patterns, not only answers',
    description:
      'A strong revision habit is to group questions by topic and notice repeated patterns. That helps you understand what the department values and prepares you better than memorizing one paper line by line.',
  },
  {
    title: 'Use community context carefully',
    description:
      'Verified uploads and discussion can save time, but the best use of community knowledge is as guidance. Always compare a solution with your own lecture notes, coursework, and the exact learning outcomes for the module.',
  },
];

export default function StoryPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 lg:px-8">
      <section className="theme-panel overflow-hidden rounded-[2rem] border">
        <div className="grid gap-8 p-8 lg:grid-cols-[1.05fr_0.95fr] lg:p-10">
          <div>
            <Badge className="theme-accent-soft mb-4 hover:bg-inherit">Student Stories And Study Tips</Badge>
            <h1 className="text-4xl font-bold text-foreground">
              UR Academic Resource Hub began with a simple need: stop losing useful academic material.
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-muted-foreground">
              This platform was designed for University of Rwanda students who needed a dependable place to find past papers, revise with confidence, and contribute resources that stay useful over time.
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Badge variant="outline">Centralized access</Badge>
              <Badge variant="outline">Community verification</Badge>
              <Badge variant="outline">Structured organization</Badge>
              <Badge variant="outline">Long-term academic archive</Badge>
            </div>
          </div>

          <div className="rounded-[1.6rem] border border-border/70 bg-muted/40 p-6">
            <BrandMark label imageClassName="h-16 w-16" labelClassName="text-2xl text-foreground" />
            <p className="mt-5 text-sm leading-7 text-muted-foreground">
              The hub combines accessibility, collaboration, verification, and practical system design so academic preparation feels less chaotic and more intentional.
            </p>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl bg-background p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Focus</p>
                <p className="mt-2 font-semibold text-foreground">Reliable UR learning resources</p>
              </div>
              <div className="rounded-2xl bg-background p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Scope</p>
                <p className="mt-2 font-semibold text-foreground">Built for UR first, scalable later</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mt-10 grid gap-5 lg:grid-cols-3">
        {pillars.map((pillar, index) => (
          <Card key={pillar.title} className="theme-panel">
            <CardHeader>
              <CardTitle className="flex items-center gap-3 text-foreground">
                {index === 0 ? (
                  <Lightbulb className="theme-section-icon h-5 w-5" />
                ) : index === 1 ? (
                  <ShieldCheck className="theme-section-icon h-5 w-5" />
                ) : (
                  <Users className="theme-section-icon h-5 w-5" />
                )}
                {pillar.title}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-7 text-muted-foreground">{pillar.description}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="theme-panel mt-10 rounded-[2rem] border p-8 lg:p-10">
        <div className="max-w-4xl">
          <h2 className="theme-title text-3xl font-bold">Why student stories matter for University of Rwanda revision</h2>
          <p className="theme-muted mt-4 text-base leading-8">
            The purpose of this page is bigger than telling the project story. It also explains why a searchable archive of <strong>University of Rwanda past papers</strong> matters in the first place. Students often improve faster when they can learn from both documents and lived experience. A paper shows the structure of an exam. A student story explains how that paper was used, what revision habits worked, and which mistakes to avoid before the next CAT or final assessment.
          </p>
          <p className="theme-muted mt-4 text-base leading-8">
            That combination is valuable for Google too, because it turns this page into meaningful, indexable content instead of decorative marketing copy. When learners search for <strong>UR exam papers</strong>, study strategies, or trusted <strong>study materials Rwanda</strong> students recommend, they should find pages that answer real questions. This section helps connect the library of papers with the study behaviors that make those resources useful.
          </p>
          <p className="theme-muted mt-4 text-base leading-8">
            If you are preparing for an upcoming assessment, start by exploring the <Link to="/resources" className="theme-link-accent font-semibold hover:underline">academic resource library</Link>, then compare what you find with the practical revision ideas below. The goal is not only to store files, but to help University of Rwanda learners study with better judgment, better context, and better access to the right material at the right time.
          </p>
        </div>
      </section>

      <section className="mt-10 grid gap-6 lg:grid-cols-2">
        <Card className="theme-panel">
          <CardHeader>
            <CardTitle className="text-foreground">Study tips students can apply with UR past papers</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {studyTips.map((tip) => (
              <div key={tip.title} className="theme-soft-panel rounded-2xl p-4">
                <h3 className="theme-title text-lg font-semibold">{tip.title}</h3>
                <p className="theme-muted mt-2 text-sm leading-7">{tip.description}</p>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="theme-panel">
          <CardHeader>
            <CardTitle className="text-foreground">How this supports search and trust</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-7 text-muted-foreground">
            <p>
              Clean navigation, readable headings, and meaningful paragraphs make this page easier for both students and search engines to understand. That matters because a good academic resource site should not hide its value behind animation or empty sections.
            </p>
            <p>
              Clear internal links also help users move naturally between the <Link to="/resources" className="theme-link-accent font-semibold hover:underline">resource library</Link>, the homepage, and the platform story. This builds a stronger information structure around the most useful content on the site.
            </p>
            <p>
              The long-term aim is simple: keep the platform discoverable, trustworthy, and genuinely helpful for University of Rwanda learners who need fast access to high-quality revision resources.
            </p>
          </CardContent>
        </Card>
      </section>

      <section className="mt-10 grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <Card className="theme-panel">
          <CardHeader>
            <CardTitle className="flex items-center gap-3 text-foreground">
              <Search className="theme-section-icon h-5 w-5" />
              What this platform is meant to do
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {features.map((feature) => (
              <div key={feature} className="rounded-2xl bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
                {feature}
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="theme-panel">
          <CardHeader>
            <CardTitle className="text-foreground">People behind it</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-2xl border border-border/70 bg-background p-5">
              <div className="flex items-center gap-4">
                <BrandMark imageClassName="h-14 w-14" />
                <div>
                  <p className="font-semibold text-foreground">Gilbert Tuyambaze</p>
                  <p className="text-sm text-muted-foreground">
                    A lead builder and creative technologist at the forefront of the project, driving its vision, shaping its experience, and turning ideas into impactful digital solutions.
                  </p>
                </div>
              </div>
              <a
                href="https://tuyambaze-gilbert.vercel.app/"
                target="_blank"
                rel="noreferrer"
                className="theme-link-accent mt-4 inline-flex items-center gap-2 text-sm font-medium hover:underline"
              >
                Visit portfolio
                <ExternalLink className="h-4 w-4" />
              </a>
            </div>

            <div className="rounded-2xl border border-border/70 bg-background p-5">
              <div className="flex items-center gap-4">
                <BrandMark imageClassName="h-14 w-14" />
                <div>
                  <p className="font-semibold text-foreground">Karly Ngarambe</p>
                  <p className="text-sm text-muted-foreground">
                    A strategic collaborator contributing to the platform&apos;s vision, shaping its story and user experience, and leading the generation of core project ideas.
                  </p>
                </div>
              </div>
              <a
                href="https://rw.linkedin.com/in/karly-ngarambe-designer"
                target="_blank"
                rel="noreferrer"
                className="theme-link-accent mt-4 inline-flex items-center gap-2 text-sm font-medium hover:underline"
              >
                Visit LinkedIn
                <ExternalLink className="h-4 w-4" />
              </a>
            </div>

            <div className="rounded-2xl bg-muted/40 p-5 text-sm leading-7 text-muted-foreground">
              The vision behind this website is not just to host files. It is to create a trustworthy academic ecosystem where revision resources, discussion, and quality control can live together in one sustainable place, shaped by people who understand the real academic pressure students face.
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
