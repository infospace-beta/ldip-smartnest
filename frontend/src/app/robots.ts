import type {MetadataRoute} from 'next';
import {publicIndexingEnabled,publicSiteOrigin} from '@/lib/public-site';
export default function robots():MetadataRoute.Robots {
  if(!publicIndexingEnabled())return {rules:{userAgent:'*',disallow:'/'}};
  return {rules:{userAgent:'*',allow:'/',disallow:['/dashboard','/api','/login','/join','/join-account','/get-started','/auth','/security','/forgot-password','/reset-password','/inspection-reports']},sitemap:`${publicSiteOrigin()}/sitemap.xml`};
}
