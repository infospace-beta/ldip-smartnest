"use client";

import Image from "next/image";
import Icon from "@/components/Icon";
import { useEffect, useState } from "react";
import { usersAPI } from "@/lib/api";

export default function UserAvatar({
  userId,
  hasAvatar,
  name,
  className,
}: {
  userId?: number;
  hasAvatar?: boolean;
  name: string;
  className: string;
}) {
  const [avatar, setAvatar] = useState<{ userId: number | undefined; url: string }>({ userId: undefined, url: "" });

  useEffect(() => {
    if (!userId || !hasAvatar) return;

    let active = true;
    let objectUrl = "";
    const loadAvatar = () => {
      usersAPI.avatar(userId)
        .then(({ data }) => {
          const nextUrl = URL.createObjectURL(data);
          if (!active) {
            URL.revokeObjectURL(nextUrl);
            return;
          }
          if (objectUrl) URL.revokeObjectURL(objectUrl);
          objectUrl = nextUrl;
          setAvatar({ userId, url: nextUrl });
        })
        .catch(() => {
          if (active) setAvatar({ userId, url: "" });
        });
    };
    loadAvatar();
    window.addEventListener("smartnest:avatar-updated", loadAvatar);

    return () => {
      active = false;
      window.removeEventListener("smartnest:avatar-updated", loadAvatar);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [hasAvatar, userId]);

  return (
    <span className={`avatar-circle ${className}`} aria-label={`${name} profile photo`}>
      {avatar.userId === userId && hasAvatar && avatar.url
        ? <Image src={avatar.url} alt="" width={96} height={96} unoptimized />
        : <Icon name="profile" />}
    </span>
  );
}
