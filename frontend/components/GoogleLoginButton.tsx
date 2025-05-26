"use client";

import { useEffect, useMemo } from "react";
import { Button } from "@heroui/react";
import { useRouter } from "next/navigation";
import { GoogleIcon, InfoIcon } from "@/components/icons";
import { Tooltip } from "@heroui/react";

interface GoogleLoginButtonProps {
  showTooltip?: boolean;
  className?: string;
}

/**
 * A reusable Google login button component with optional tooltip and auto-click functionality on localhost
 */
export const GoogleLoginButton = ({ showTooltip = true, className = "" }: GoogleLoginButtonProps) => {
  const router = useRouter();
  const apiUrl = process.env.NEXT_PUBLIC_API_URL!;

  const handleGoogleLogin = () => {
    router.push(`${apiUrl}/login`);
  };
  
  useEffect(() => {
    // Only run auto-login on localhost after 3 seconds
    if (typeof window !== 'undefined' && window.location.hostname === 'localhost') {
      setTimeout(handleGoogleLogin, 3000);
    }
  }, [handleGoogleLogin]);
  
  const loginTooltipContent = (
    <div className="px-1 py-2 max-w-xs">
      <div className="text-sm font-bold mb-1">Beta Users Only</div>
      <div className="text-xs">
        This login is only for existing beta users. If you're not a beta user yet, please join our waitlist
        below.
      </div>
    </div>
  );
  
  const button = useMemo(() => (
    <Button
      className={`text-sm font-normal text-default-600 bg-default-100 ${className}`}
      data-testid="GoogleLogin"
      endContent={<InfoIcon className="text-default-400" size={14} />}
      startContent={<GoogleIcon className="text-danger" />}
      variant="flat"
      onPress={handleGoogleLogin}
    >
      Login with Google
    </Button>
  ), [className, handleGoogleLogin]);

  if (!showTooltip) {
    return button;
  }

  return (
    <Tooltip
      closeDelay={0}
      color="foreground"
      content={loginTooltipContent}
      delay={200}
      placement="bottom"
    >
      {button}
    </Tooltip>
  );
}; 