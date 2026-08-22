import { useState } from 'react';
import { FileUp, Plus, Save, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import InlineFieldMessage from './InlineFieldMessage';
import { normalizeApiError } from '@/lib/api-errors';
import { normalizeIsbn, normalizeText, normalizeUnique, buildStorageKey } from '@/lib/normalization';
import { uploadFileObject } from '@/lib/client';
import { fetchModules, searchCourses, updateBook, updateBookAuthors, updateBookCourses, updateBookModules, replaceBookFile, replaceBookCover, type Book, type Course, type Module } from '@/lib/books';
import { toast } from '@/lib/messages';

type Props = { book: Book; canManage: boolean; onUpdated: (book: Book) => void };
const languages = [['en', 'English'], ['fr', 'French'], ['rw', 'Kinyarwanda'], ['sw', 'Swahili'], ['ar', 'Arabic'], ['zh', 'Chinese'], ['es', 'Spanish'], ['pt', 'Portuguese'], ['de', 'German'], ['it', 'Italian'], ['ja', 'Japanese'], ['ko', 'Korean'], ['hi', 'Hindi'], ['ru', 'Russian'], ['other', 'Other']];

export default function BookManagementEditor({ book, canManage, onUpdated }: Props) {
  const [title, setTitle] = useState(book.title);
  const [description, setDescription] = useState(book.description || '');
  const [isbn, setIsbn] = useState(book.isbn || '');
  const [language, setLanguage] = useState(book.language || 'other');
  const [authors, setAuthors] = useState(book.authors);
  const [authorInput, setAuthorInput] = useState('');
  const [courses, setCourses] = useState(book.courses || []);
  const [modules, setModules] = useState(book.modules || []);
  const [courseQuery, setCourseQuery] = useState('');
  const [moduleQuery, setModuleQuery] = useState('');
  const [courseOptions, setCourseOptions] = useState<Course[]>([]);
  const [moduleOptions, setModuleOptions] = useState<Module[]>([]);
  const [newFile, setNewFile] = useState<File | null>(null);
  const [newCover, setNewCover] = useState<File | null>(null);
  const [saving, setSaving] = useState(false);
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  const isbnValue = normalizeIsbn(isbn);
  const titleError = touched.title && !title.trim() ? 'Title is required.' : undefined;
  const isbnError = touched.isbn && isbn.trim() && !isbnValue ? 'Enter a valid ISBN-10 or ISBN-13, or leave it blank.' : undefined;
  const authorsError = touched.authors && !authors.length ? 'Add at least one author.' : undefined;
  const coursesError = touched.courses && !courses.length ? 'Select at least one course.' : undefined;
  const markTouched = (field: string) => setTouched((current) => ({ ...current, [field]: true }));

  const save = async () => {
    const nextTouched = { title: true, isbn: true, authors: true, courses: true };
    setTouched((current) => ({ ...current, ...nextTouched }));
    if (!title.trim() || (isbn.trim() && !isbnValue) || !authors.length || !courses.length) return;
    setSaving(true);
    try {
      let updated = await updateBook(book.id, { title: normalizeText(title), description: normalizeText(description) || null, isbn: isbnValue || null, language });
      updated = await updateBookAuthors(updated.id, normalizeUnique(authors));
      updated = await updateBookCourses(updated.id, courses.map((course) => course.id));
      updated = await updateBookModules(updated.id, normalizeUnique(modules.map((module) => module.id)));
      onUpdated(updated);
      toast.success('Book metadata and academic associations updated.');
    } catch (error) {
      toast.error(normalizeApiError(error).message || 'Unable to update Book metadata.');
    } finally {
      setSaving(false);
    }
  };

  const replaceResource = async (file: File, kind: 'file' | 'cover') => {
    const valid = kind === 'file' ? /\.(pdf|epub)$/i.test(file.name) || ['application/pdf', 'application/epub+zip'].includes(file.type) : file.type.startsWith('image/');
    if (!valid) { toast.error(kind === 'file' ? 'Choose a PDF or EPUB file.' : 'Choose an image cover.'); return; }
    setSaving(true);
    try {
      const namespace = kind === 'file' ? 'books' : 'book-covers';
      const key = buildStorageKey('books', namespace, file.name, `${book.id}-${Date.now()}`);
      const storedKey = await uploadFileObject('books', key, file);
      const updated = kind === 'file'
        ? await replaceBookFile(book.id, { key: storedKey, original_filename: file.name, mime_type: file.type, size: file.size })
        : await replaceBookCover(book.id, { key: storedKey, original_filename: file.name, mime_type: file.type, size: file.size });
      onUpdated(updated);
      if (kind === 'file') setNewFile(null); else setNewCover(null);
      toast.success(kind === 'file' ? 'Book file updated.' : 'Book cover updated.');
    } catch (error) {
      toast.error(normalizeApiError(error).message || 'The replacement could not be completed.');
    } finally { setSaving(false); }
  };

  return <div className="space-y-6 border-t pt-5">
    <section className="space-y-3"><h3 className="theme-title text-base font-semibold">Metadata</h3><div className="grid gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2"><Label htmlFor="book-edit-title">Title</Label><Input id="book-edit-title" value={title} onChange={(event) => setTitle(event.target.value)} onBlur={() => markTouched('title')} aria-invalid={Boolean(titleError)} aria-describedby="book-edit-title-error" disabled={!canManage || saving} /><InlineFieldMessage id="book-edit-title-error" message={titleError} /></div>
      <div><Label htmlFor="book-edit-isbn">ISBN</Label><Input id="book-edit-isbn" value={isbn} onChange={(event) => setIsbn(event.target.value)} onBlur={() => markTouched('isbn')} aria-invalid={Boolean(isbnError)} aria-describedby="book-edit-isbn-error" disabled={!canManage || saving} /><InlineFieldMessage id="book-edit-isbn-error" message={isbnError} />{isbn.trim() && isbnValue && isbnValue !== isbn.trim() && <InlineFieldMessage tone="info" automatic message="ISBN formatted automatically." />}</div>
      <div><Label htmlFor="book-edit-language">Language</Label><select id="book-edit-language" value={language} onChange={(event) => setLanguage(event.target.value)} disabled={!canManage || saving} className="theme-form-input mt-2 h-10 w-full rounded-md border px-3">{languages.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
      <div className="sm:col-span-2"><Label htmlFor="book-edit-description">Description</Label><Textarea id="book-edit-description" value={description} onChange={(event) => setDescription(event.target.value)} disabled={!canManage || saving} /></div>
    </div></section>
    <section className="space-y-3"><h3 className="theme-title text-base font-semibold">Authors</h3><div className="flex gap-2"><Input value={authorInput} onChange={(event) => setAuthorInput(event.target.value)} placeholder="Add author" disabled={!canManage || saving} /><Button type="button" variant="outline" onClick={() => { const value = normalizeText(authorInput); if (value) { setAuthors((current) => normalizeUnique([...current, value])); setAuthorInput(''); } }} disabled={!canManage || saving}><Plus className="mr-1 h-4 w-4" />Add</Button></div><InlineFieldMessage message={authorsError} /><div className="flex flex-wrap gap-2">{authors.map((author) => <span key={author} className="rounded-full bg-muted px-3 py-1 text-sm">{author}<button type="button" className="ml-2" aria-label={`Remove ${author}`} onClick={() => setAuthors((current) => current.filter((item) => item !== author))} disabled={!canManage || saving}><X className="inline h-3 w-3" /></button></span>)}</div></section>
    <section className="space-y-3"><h3 className="theme-title text-base font-semibold">Academic associations</h3><div><Label htmlFor="book-course-search">Courses</Label><Input id="book-course-search" value={courseQuery} onChange={(event) => { const value = event.target.value; setCourseQuery(value); if (value.trim()) void searchCourses(value).then((result) => setCourseOptions(result.items)).catch(() => setCourseOptions([])); else setCourseOptions([]); }} onBlur={() => markTouched('courses')} disabled={!canManage || saving} placeholder="Search courses" /><InlineFieldMessage message={coursesError} /><div className="mt-2 flex flex-wrap gap-2">{courses.map((course) => <span key={course.id} className="rounded-full bg-muted px-3 py-1 text-sm">{course.code || course.name}<button type="button" className="ml-2" aria-label={`Remove ${course.name}`} onClick={() => setCourses((current) => current.filter((item) => item.id !== course.id))} disabled={!canManage || saving}><X className="inline h-3 w-3" /></button></span>)}</div>{courseOptions.map((course) => <Button key={course.id} type="button" size="sm" variant="outline" className="mr-2 mt-2" onClick={() => { setCourses((current) => current.some((item) => item.id === course.id) ? current : [...current, course]); setCourseOptions([]); setCourseQuery(''); }}>{course.code || course.name}</Button>)}</div><div><Label htmlFor="book-module-search">Modules</Label><Input id="book-module-search" value={moduleQuery} onChange={(event) => { const value = event.target.value; setModuleQuery(value); void fetchModules(value).then((result) => setModuleOptions(result.items)).catch(() => setModuleOptions([])); }} disabled={!canManage || saving} placeholder="Search modules" /><div className="mt-2 flex flex-wrap gap-2">{modules.map((module) => <span key={module.id} className="rounded-full bg-muted px-3 py-1 text-sm">{module.code || module.name}<button type="button" className="ml-2" aria-label={`Remove ${module.name}`} onClick={() => setModules((current) => current.filter((item) => item.id !== module.id))} disabled={!canManage || saving}><X className="inline h-3 w-3" /></button></span>)}</div>{moduleOptions.map((module) => <Button key={module.id} type="button" size="sm" variant="outline" className="mr-2 mt-2" onClick={() => { setModules((current) => current.some((item) => item.id === module.id) ? current : [...current, module]); setModuleOptions([]); setModuleQuery(''); }}>{module.code || module.name}</Button>)}</div></section>
    <section className="space-y-3"><h3 className="theme-title text-base font-semibold">File and cover</h3><div className="grid gap-3 sm:grid-cols-2"><div><p className="theme-muted text-sm">Current file: {book.file_name || 'Not provided'}</p><Input id="book-replace-file" type="file" accept=".pdf,.epub,application/pdf,application/epub+zip" onChange={(event) => setNewFile(event.target.files?.[0] || null)} disabled={!canManage || saving} /><Button type="button" variant="outline" className="mt-2" onClick={() => newFile && void replaceResource(newFile, 'file')} disabled={!newFile || !canManage || saving}><FileUp className="mr-1 h-4 w-4" />Replace file</Button></div><div><p className="theme-muted text-sm">Current cover: {book.cover_key ? 'Available' : 'Not provided'}</p><Input id="book-replace-cover" type="file" accept="image/*" onChange={(event) => setNewCover(event.target.files?.[0] || null)} disabled={!canManage || saving} /><Button type="button" variant="outline" className="mt-2" onClick={() => newCover && void replaceResource(newCover, 'cover')} disabled={!newCover || !canManage || saving}><FileUp className="mr-1 h-4 w-4" />Replace cover</Button></div></div></section>
    <Button type="button" className="w-full" onClick={() => void save()} disabled={!canManage || saving}><Save className="mr-1 h-4 w-4" />{saving ? 'Saving…' : 'Save Book changes'}</Button>
  </div>;
}
