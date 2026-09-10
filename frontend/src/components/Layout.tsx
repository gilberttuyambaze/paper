import { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import BrandMark from '@/components/BrandMark';
import AvatarFallback from '@/components/AvatarFallback';
import SeoMeta from '@/components/SeoMeta';
import { useAuth } from '@/contexts/AuthContext';
import { fetchNotifications } from '@/lib/client';
import { fetchUserProfile, getStorageDownloadUrl } from '@/lib/client';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import {
  BookOpen,
  Upload,
  LayoutDashboard,
  Shield,
  Menu,
  User,
  LogOut,
  LogIn,
  UserCircle2,
  Search,
  Moon,
  Sun,
  Bell,
} from 'lucide-react';

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  const { user, login, logout, hasPermission } = useAuth();
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [mobileOpen, setMobileOpen] = useState(false);
  const [notificationCount, setNotificationCount] = useState(0);
  const [profileImageUrl, setProfileImageUrl] = useState<string | null>(null);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const storedTheme = localStorage.getItem('ur-theme');
    if (storedTheme === 'light' || storedTheme === 'dark') {
      setTheme(storedTheme);
      return;
    }

    setTheme('light');
  }, []);

  useEffect(() => {
    const applyTheme = (nextTheme: 'light' | 'dark') => {
      const isDark = nextTheme === 'dark';
      document.documentElement.classList.toggle('dark', isDark);
    };

    applyTheme(theme);
    localStorage.setItem('ur-theme', theme);
  }, [theme]);

  useEffect(() => {
    if (!user) {
      setNotificationCount(0);
      return;
    }

    void fetchNotifications()
      .then((items) => setNotificationCount(items.filter((item) => !item.is_read).length))
      .catch(() => setNotificationCount(0));
  }, [user, location.pathname]);

  useEffect(() => {
    let mounted = true;
    async function loadProfileImage() {
      try {
        const profile = await fetchUserProfile();
        if (!mounted) return;
        if (!profile || !profile.profile_picture_key) {
          setProfileImageUrl(null);
          return;
        }

        // If the key is an external URL, use it directly.
        if (/^https?:\/\//i.test(profile.profile_picture_key)) {
          setProfileImageUrl(profile.profile_picture_key);
          return;
        }

        const url = await getStorageDownloadUrl('profiles', profile.profile_picture_key);
        if (mounted) setProfileImageUrl(url);
      } catch (e) {
        if (mounted) setProfileImageUrl(null);
      }
    }

    if (user) void loadProfileImage();
    return () => {
      mounted = false;
    };
  }, [user]);

  const navItems = [
    { path: '/', label: 'Home', icon: BookOpen },
    { path: '/resources', label: 'Browse Resources', icon: Search },
    { path: '/upload', label: 'Upload', icon: Upload, auth: true, permission: 'books.create' },
    { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard, auth: true },
  ];
  const canUpload = hasPermission('books.create');
  const canAccessManagement = hasPermission('admin.dashboard.view');
  const managementPath = user?.role === 'content_manager' ? '/content-manager' : '/admin';
  const managementLabel = user?.role === 'content_manager' ? 'Content Manager' : 'Admin';
  const seoConfig = (() => {
    if (location.pathname === '/' || location.pathname === '/study-resources') {
      return {
        title: 'University of Rwanda academic resources',
        description:
          'Find University of Rwanda past papers, academic books, and study materials that students can search, compare, and use for focused revision.',
        canonicalPath: location.pathname === '/study-resources' ? '/study-resources' : '/',
      };
    }

    if (location.pathname === '/resources') {
      return {
        title: 'University of Rwanda academic resources',
        description:
          'Browse University of Rwanda past papers, academic books, and study resources. Filter by resource type, course, module, year, uploader, language, and more.',
        canonicalPath: '/resources',
      };
    }

    if (location.pathname === '/student-stories' || location.pathname === '/story') {
      return {
        title: 'Student stories and study tips for University of Rwanda learners',
        description:
          'Read student stories, revision tips, and study strategies based on how University of Rwanda learners use past papers and study materials Rwanda students trust.',
        canonicalPath: location.pathname === '/student-stories' ? '/student-stories' : '/story',
      };
    }

    if (location.pathname === '/terms') {
      return {
        title: 'Terms of use for UR Academic Resource Hub',
        description:
          'Read the terms for using University of Rwanda past papers, UR exam papers, and study materials Rwanda students share through the platform.',
        canonicalPath: '/terms',
      };
    }

    if (location.pathname === '/privacy') {
      return {
        title: 'Privacy policy for UR Academic Resource Hub',
        description:
          'Learn how UR Academic Resource Hub handles profile data, uploads, and study materials Rwanda platform activity for University of Rwanda learners.',
        canonicalPath: '/privacy',
      };
    }

    if (location.pathname.startsWith('/paper/')) {
      return {
        title: 'UR exam paper details and study discussion',
        description:
          'View a University of Rwanda past paper, read comments, study discussion, and related study materials Rwanda learners use for revision.',
        canonicalPath: location.pathname,
      };
    }

    if (location.pathname.startsWith('/book/')) {
      return {
        title: 'Academic book details and study discussion',
        description: 'Open a public academic book, read its details, view the document, and join the discussion.',
        canonicalPath: location.pathname,
      };
    }

    if (location.pathname === '/upload') {
      return {
        title: 'Upload University of Rwanda past papers',
        description: 'Private page for uploading UR exam papers and study materials Rwanda contributors want to share.',
        canonicalPath: '/upload',
        robots: 'noindex,nofollow',
      };
    }

    if (location.pathname === '/dashboard') {
      return {
        title: 'Dashboard',
        description: 'Private dashboard for uploads, notifications, and contribution tracking.',
        canonicalPath: '/dashboard',
        robots: 'noindex,nofollow',
      };
    }

    if (location.pathname === '/profile') {
      return {
        title: 'Profile',
        description: 'Private profile management for UR Academic Resource Hub.',
        canonicalPath: '/profile',
        robots: 'noindex,nofollow',
      };
    }

    if (location.pathname === '/admin' || location.pathname === '/content-manager') {
      return {
        title: 'Management Dashboard',
        description: 'Private management dashboard for moderation and platform administration.',
        canonicalPath: location.pathname,
        robots: 'noindex,nofollow',
      };
    }

    return {
      title: 'UR Academic Resource Hub',
      description:
        'Find University of Rwanda past papers, UR exam papers, and study materials Rwanda students can browse, search, and discuss.',
      canonicalPath: location.pathname,
    };
  })();

  const isActive = (path: string) => location.pathname === path;
  const navLinkClass = (active: boolean) =>
    `theme-nav-link flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
      active ? 'theme-nav-link--active' : ''
    }`;

  return (
    <div className="theme-shell">
      <SeoMeta {...seoConfig} />
      <header className="theme-nav-surface sticky top-0 z-50 shadow-lg">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            <Link to="/" className="flex items-center gap-2 transition-opacity hover:opacity-90">
              <BrandMark
                label
                imageClassName="h-10 w-10"
                labelClassName={user ? "brand-label text-lg md:hidden min-[844px]:block" : "brand-label text-lg"}
              />
            </Link>

            <nav className="hidden items-center gap-1 md:flex">
              {navItems.map((item) => {
                if (item.auth && !user) return null;
                if (item.permission && !hasPermission(item.permission)) return null;
                const Icon = item.icon;

                return (
                  <Link key={item.path} to={item.path} className={navLinkClass(isActive(item.path))}>
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                );
              })}
              {canAccessManagement && (
                <Link to={managementPath} className={navLinkClass(isActive('/admin') || isActive('/content-manager'))}>
                  <Shield className="h-4 w-4" />
                  {managementLabel}
                </Link>
              )}
            </nav>

            <div className="flex items-center gap-2">
              <div className="theme-control-group flex items-center space-x-2 rounded-full p-1 backdrop-blur">
                <Button
                  type="button"
                  variant={theme === 'light' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setTheme('light')}
                  className="h-8 w-8 rounded-full p-0"
                  aria-label="Switch to light mode"
                  title="Switch to light mode"
                >
                  <Sun className="h-4 w-4" />
                </Button>
                <Button
                  type="button"
                  variant={theme === 'dark' ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => setTheme('dark')}
                  className="h-8 w-8 rounded-full p-0"
                  aria-label="Switch to dark mode"
                  title="Switch to dark mode"
                >
                  <Moon className="h-4 w-4" />
                </Button>
              </div>

              {user ? (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => navigate('/dashboard#notifications')}
                    className="theme-icon-button relative"
                  >
                    <Bell className="h-5 w-5" />
                    {notificationCount > 0 && (
                      <span className="theme-accent-bg absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px]">
                        {notificationCount}
                      </span>
                    )}
                  </Button>

                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="theme-icon-button overflow-hidden rounded-full p-0" aria-label="Open account menu">
                        <AvatarFallback name={user.name || user.email} imageUrl={profileImageUrl ?? undefined} imageAlt="Account avatar" className="text-xs" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent
                      align="end"
                      className="theme-dropdown-surface w-48"
                    >
                      <div className="theme-dropdown-muted px-2 py-1.5 text-sm">{user.email || 'Logged in'}</div>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onClick={() => navigate('/profile')}>
                        <UserCircle2 className="mr-2 h-4 w-4" />
                        My Profile
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onClick={() => navigate('/dashboard')}>
                        <LayoutDashboard className="mr-2 h-4 w-4" />
                        Dashboard
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onClick={async () => {
                          await logout();
                          navigate('/');
                        }}
                      >
                        <LogOut className="mr-2 h-4 w-4" />
                        Logout
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </>
              ) : (
                <Button onClick={login} className="theme-accent-bg text-sm" size="sm">
                  <LogIn className="mr-2 h-4 w-4" />
                  Sign In
                </Button>
              )}

              <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
                <SheetTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="theme-icon-button md:hidden"
                  >
                    <Menu className="h-5 w-5" />
                  </Button>
                </SheetTrigger>
                <SheetContent side="right" className="theme-nav-surface w-64 border-none">
                  <SheetHeader className="sr-only">
                    <SheetTitle>Mobile navigation menu</SheetTitle>
                    <SheetDescription>
                      Browse pages, access uploads, open the dashboard, and reach admin tools from the mobile menu.
                    </SheetDescription>
                  </SheetHeader>
                  <div className="mt-8 flex flex-col gap-2">
                    {user && (
                      <Link
                        to="/profile"
                        onClick={() => setMobileOpen(false)}
                        className={`flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-colors ${
                          isActive('/profile') ? 'theme-accent-bg' : 'theme-mobile-link'
                        }`}
                      >
                        <UserCircle2 className="h-5 w-5" />
                        My Profile
                      </Link>
                    )}
                    {navItems.map((item) => {
                      if (item.auth && !user) return null;
                      if (item.permission && !hasPermission(item.permission)) return null;
                      const Icon = item.icon;

                      return (
                        <Link
                          key={item.path}
                          to={item.path}
                          onClick={() => setMobileOpen(false)}
                          className={`flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-colors ${
                            isActive(item.path) ? 'theme-accent-bg' : 'theme-mobile-link'
                          }`}
                        >
                          <Icon className="h-5 w-5" />
                          {item.label}
                        </Link>
                      );
                    })}
                    {canAccessManagement && (
                      <Link
                        to={managementPath}
                        onClick={() => setMobileOpen(false)}
                        className={`flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-medium transition-colors ${
                          isActive('/admin') || isActive('/content-manager') ? 'theme-accent-bg' : 'theme-mobile-link'
                        }`}
                      >
                        <Shield className="h-5 w-5" />
                        {managementLabel}
                      </Link>
                    )}
                  </div>
                </SheetContent>
              </Sheet>
            </div>
          </div>
        </div>
      </header>

      <main>{children}</main>

      <footer className="theme-footer mt-16 py-8">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-8 md:grid-cols-2 xl:grid-cols-4">
            <div>
              <div className="mb-3">
                <BrandMark label imageClassName="h-8 w-8" labelClassName="theme-title" />
              </div>
              <p className="theme-muted text-sm">
                A collaborative platform for University of Rwanda students to share and access academic resources.
              </p>
            </div>
            <div>
              <h3 className="theme-title mb-3 font-semibold">Quick Links</h3>
              <div className="theme-muted flex flex-col gap-2 text-sm">
                <Link to="/" className="transition-colors hover:text-primary">Home</Link>
                <Link to="/resources" className="transition-colors hover:text-primary">Browse Resources</Link>
                {canUpload && <Link to="/upload" className="transition-colors hover:text-primary">Upload</Link>}
                <Link to="/student-stories" className="transition-colors hover:text-primary">Story Behind This Website</Link>
              </div>
            </div>
            <div>
              <h3 className="theme-title mb-3 font-semibold">Policy</h3>
              <div className="theme-muted flex flex-col gap-2 text-sm">
                <Link to="/terms" className="transition-colors hover:text-primary">Terms</Link>
                <Link to="/privacy" className="transition-colors hover:text-primary">Privacy Policy</Link>
                
              </div>
            </div>
            <div>
              <h3 className="theme-title mb-3 font-semibold">Credits</h3>
              <p className="theme-muted text-sm">
                Led by Gilbert Tuyambaze with  Karly Ngarambe, inspired by the need for a reliable UR academic archive.
              </p>
              <div className="theme-muted mt-3 flex flex-col gap-2 text-sm">
                <a
                  href="https://tuyambaze-gilbert.vercel.app/"
                  target="_blank"
                  rel="noreferrer"
                  className="transition-colors hover:text-primary"
                >
                  Gilbert Tuyambaze
                </a>
                <a
                  href="https://rw.linkedin.com/in/karly-ngarambe-designer"
                  target="_blank"
                  rel="noreferrer"
                  className="transition-colors hover:text-primary"
                >
                  Karly Ngarambe
                </a>
              </div>
            </div>
          </div>
          <div className="theme-muted mt-8 border-t border-border/70 pt-6 text-center text-sm">
            Copyright 2026 UR Academic Resource Hub. Led by{' '}
            <a href="https://tuyambaze-gilbert.vercel.app/" target="_blank" rel="noreferrer" className="hover:text-primary">
              Gilbert Tuyambaze
            </a>{' '}
            with {' '}
            <a
              href="https://rw.linkedin.com/in/karly-ngarambe-designer"
              target="_blank"
              rel="noreferrer"
              className="hover:text-primary"
            >
              Karly Ngarambe
            </a>
            .
          </div>
        </div>
      </footer>
    </div>
  );
}
