import { useEffect, useState } from 'react';
import { fetchPublicSiteAccessSettings, type PublicSiteAccessSettings } from '@/lib/client';
import { useAuth } from '@/contexts/AuthContext';

export type UploadResourceType = 'book' | 'paper';

function normalizeRole(role: string | undefined) {
  return (role || '').trim().toLowerCase();
}

export function useUploadAccess() {
  const { user, loading: authLoading } = useAuth();
  const [settings, setSettings] = useState<PublicSiteAccessSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let mounted = true;

    if (authLoading) {
      setLoading(true);
      setError(null);
      return () => {
        mounted = false;
      };
    }

    setSettings(null);
    setLoading(true);
    setError(null);

    void fetchPublicSiteAccessSettings()
      .then((nextSettings) => {
        if (!mounted) return;
        setSettings(nextSettings);
      })
      .catch((requestError) => {
        if (!mounted) return;
        setSettings(null);
        setError(requestError);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [authLoading, user?.id]);

  const allowedResourceTypes = (settings?.allowed_resource_types || []).filter(
    (resourceType): resourceType is UploadResourceType => resourceType === 'book' || resourceType === 'paper'
  );
  const role = normalizeRole(user?.role);
  const accessByMode = settings?.upload_access_mode === 'authenticated'
    ? Boolean(user)
    : settings?.upload_access_mode === 'selected_roles'
      ? Boolean(user && settings.upload_roles.map(normalizeRole).includes(role))
      : false;
  const canAccessUploadArea = !loading && !error && accessByMode && allowedResourceTypes.length > 0;

  return {
    settings,
    canAccessUploadArea,
    allowedResourceTypes,
    loading,
    error,
  };
}
