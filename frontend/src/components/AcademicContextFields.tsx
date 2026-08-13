import { useEffect, useMemo, useState } from 'react';
import { fetchAcademicTaxonomy, fetchProgrammeRecommendations, createProgrammeSubmission, type AcademicNode, type AcademicTaxonomy, type ProgrammeRecommendation } from '@/lib/client';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export type AcademicContextValue = { institution_id: string; campus_id: string; college_id: string; school_id: string; programme_id: string };
const empty = { institution_id: 'ur', campus_id: '', college_id: '', school_id: '', programme_id: '' };

export default function AcademicContextFields({ value, onChange, otherName = '', onOtherNameChange, title = 'Academic information', paper = false, submissionSource }: { value: AcademicContextValue; onChange: (value: AcademicContextValue) => void; otherName?: string; onOtherNameChange?: (value: string) => void; title?: string; paper?: boolean; submissionSource?: string }) {
  const [taxonomy, setTaxonomy] = useState<AcademicTaxonomy | null>(null);
  const [error, setError] = useState('');
  const [matches, setMatches] = useState<ProgrammeRecommendation[]>([]);
  const [matching, setMatching] = useState(false);

  useEffect(() => {
    fetchAcademicTaxonomy().then(setTaxonomy).catch(() => setError('Academic information could not load. Please try again.'));
  }, []);

  const children = (parent: string) => taxonomy?.nodes.filter(n => n.parent_id === parent).sort((a, b) => a.order - b.order) || [];

  const set = (key: keyof AcademicContextValue, id: string) => {
    const next = { ...value, [key]: id };
    if (key === 'campus_id') Object.assign(next, { college_id: '', school_id: '', programme_id: '' });
    if (key === 'college_id') Object.assign(next, { school_id: '', programme_id: '' });
    if (key === 'school_id') next.programme_id = '';
    onChange(next);
    setMatches([]);
  };

  const recommend = async (text?: string) => {
    const candidate = ((text ?? otherName) || '').trim();
    if (!candidate || candidate.length < 3 || !value.campus_id || !value.college_id || !value.school_id) {
      setMatches([]);
      return;
    }
    setMatching(true);
    try {
      const recs = await fetchProgrammeRecommendations({ ...value, programme_name_other: candidate });
      setMatches(recs || []);
    } catch (e) {
      setMatches([]);
    } finally {
      setMatching(false);
    }
  };

  // debounce recommendations while typing — must be declared unconditionally before any returns
  useEffect(() => {
    const t = setTimeout(() => { void recommend(otherName); }, 350);
    return () => clearTimeout(t);
  }, [otherName, value.campus_id, value.college_id, value.school_id]);

  const field = (label: string, key: keyof AcademicContextValue, options: AcademicNode[], disabled: boolean, placeholder: string) => (
    <div>
      <Label className="theme-form-label">{label}</Label>
      <Select value={value[key]} onValueChange={id => set(key, id)} disabled={disabled}>
        <SelectTrigger className="theme-form-input mt-2 h-12 rounded-xl">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {options.map(option => <SelectItem key={option.id} value={option.id}>{option.name}</SelectItem>)}
          {key === 'programme_id' && value.school_id && <SelectItem value="other">Programme not listed</SelectItem>}
        </SelectContent>
      </Select>
    </div>
  );

  if (error) return <div className="theme-soft-panel rounded-xl p-3 text-sm" role="alert">{error} <button type="button" className="underline" onClick={() => { setError(''); fetchAcademicTaxonomy().then(setTaxonomy).catch(() => setError('Academic information could not load. Please try again.')); }}>Retry</button></div>;
  if (!taxonomy) return <p className="theme-muted text-sm">Loading academic information…</p>;

  const campuses = children('ur');
  const colleges = children(value.campus_id);
  const schools = children(value.college_id);
  const programmes = children(value.school_id);


  return (
    <section className="space-y-3">
      <div>
        <h3 className="theme-title text-base font-semibold">{title}</h3>
        <p className="theme-muted text-sm">{paper ? 'Choose where this paper belongs. This does not change your profile.' : 'Select the academic programme you currently study.'}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {field('Campus', 'campus_id', campuses, false, 'Select campus')}
        {field('College', 'college_id', colleges, !value.campus_id, value.campus_id ? 'Select college' : 'Select a campus first')}
        {field('School', 'school_id', schools, !value.college_id, value.college_id ? 'Select school' : 'Select a college first')}
        {field('Academic programme', 'programme_id', programmes, !value.school_id, programmes.length ? 'Select programme' : value.school_id ? 'Programme not listed' : 'Select a school first')}
      </div>

      {value.programme_id === 'other' && (
        <div className="theme-soft-panel rounded-xl p-4">
          <Label className="theme-form-label">Enter your programme</Label>
          <div className="mt-2 flex gap-2">
            <Input value={otherName} maxLength={180} onChange={(event) => onOtherNameChange?.(event.target.value)} className="theme-form-input" placeholder="Your programme name" />
            <Button type="button" variant="outline" onClick={() => void recommend()} disabled={matching}>{matching ? 'Finding…' : 'Find matches'}</Button>
          </div>

          <div className="mt-3">
                  {matching && <p className="theme-muted text-sm">Finding matches…</p>}
            {!matching && matches.length > 0 && matches.map((match) => (
              <div key={`${match.kind}-${match.id}`} className="mt-3 text-sm theme-border p-3 rounded">
                <p className="theme-title">{match.name} <span className="theme-muted">· {match.confidence}% · {match.confidence_label}</span></p>
                <p className="theme-muted">{match.occurrences} students · {match.campus_id} → {match.college_id} → {match.school_id}</p>
                <div className="mt-2 flex gap-2">
                  {match.kind === 'official' ? (
                    <>
                      <Button onClick={() => { onChange({ ...value, programme_id: match.id }); onOtherNameChange?.(''); }}>Use this programme</Button>
                      <Button variant="ghost" onClick={async () => {
                        try {
                          await createProgrammeSubmission({ institution_id: 'ur', campus_id: value.campus_id, college_id: value.college_id, school_id: value.school_id, programme_name_other: otherName, source: submissionSource || (paper ? 'paper_upload' : 'profile') });
                          onOtherNameChange?.('');
                        } catch (e) {
                          // non-blocking
                          console.error('Failed to save submission', e);
                        }
                      }}>Keep my programme</Button>
                    </>
                  ) : (
                    <>
                      <Button onClick={async () => {
                        try {
                          await createProgrammeSubmission({ institution_id: 'ur', campus_id: value.campus_id, college_id: value.college_id, school_id: value.school_id, programme_name_other: otherName, source: submissionSource || (paper ? 'paper_upload' : 'profile') });
                          onOtherNameChange?.('');
                        } catch (e) { console.error('Failed to save submission', e); }
                      }}>Keep my programme</Button>
                    </>
                  )}
                </div>
              </div>
            ))}

            {!matching && matches.length === 0 && otherName.trim().length >= 3 && (
              <p className="theme-muted text-sm">We couldn't find a recommendation — your entry will be saved for review.</p>
            )}
          </div>
        </div>
      )}

      {value.school_id && programmes.length === 0 && <p className="theme-muted text-xs">No programmes are currently listed for this school. Choose “Programme not listed” to enter a new programme.</p>}
    </section>
  );
}
