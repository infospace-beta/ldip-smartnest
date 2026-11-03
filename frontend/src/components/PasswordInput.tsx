"use client";

import { useState, type InputHTMLAttributes } from "react";
import Icon from "@/components/Icon";

export default function PasswordInput(props: Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  const [visible, setVisible] = useState(false);
  return (
    <span className="password-input-wrap">
      <input {...props} type={visible ? "text" : "password"} />
      <button className="password-visibility" type="button" disabled={props.disabled}
        aria-label={visible ? "Hide password" : "Show password"} aria-pressed={visible}
        onClick={() => setVisible((value) => !value)}>
        <Icon name={visible ? "eye-off" : "eye"} />
      </button>
    </span>
  );
}
