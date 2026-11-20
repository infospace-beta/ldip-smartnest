import type {MetadataRoute} from 'next';
import {publicIndexingEnabled,publicSiteOrigin} from '@/lib/public-site';
export default function sitemap():MetadataRoute.Sitemap {
  if(!publicIndexingEnabled())return [];
  return [{url:`${publicSiteOrigin()}/`,changeFrequency:'monthly',priority:1}];
}
