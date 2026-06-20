import { useTheme } from "next-themes";
import { Toaster as Sonner, toast } from "sonner";

type ToasterProps = React.ComponentProps<typeof Sonner>;

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme = "system" } = useTheme();

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      position="bottom-right"
      visibleToasts={3}
      toastOptions={{
        unstyled: false,
        classNames: {
          toast: [
            "group toast theme-classic",
            "!bg-[var(--bg-elevated)] !text-[var(--fg)] !border !border-[var(--border-strong)] !rounded-none",
            "!shadow-[0_16px_48px_-16px_rgba(20,15,12,0.25),0_4px_12px_-4px_rgba(20,15,12,0.12)]",
            "!font-sans !p-4 !gap-2.5",
          ].join(" "),
          title: "!font-display !font-medium !text-[14px] !tracking-[-0.005em] !text-[var(--fg)]",
          description: "!text-[12px] !text-[var(--fg-muted)] !leading-relaxed",
          actionButton: "!bg-[var(--brand)] !text-[var(--brand-fg)] !rounded-[3px] !font-sans !font-medium !text-[12px] !tracking-[0.03em] !px-3 !py-1.5",
          cancelButton: "!bg-transparent !border !border-[var(--border-strong)] !text-[var(--fg-muted)] !rounded-[3px] !font-sans !text-[12px]",
          icon: "!text-[var(--brand)]",
          success: "!border-l-[3px] !border-l-[#2f8a5d] [&_[data-icon]]:!text-[#2f8a5d]",
          info: "!border-l-[3px] !border-l-[var(--brand)] [&_[data-icon]]:!text-[var(--brand)]",
          warning: "!border-l-[3px] !border-l-[#c47a1e] [&_[data-icon]]:!text-[#c47a1e]",
          error: "!border-l-[3px] !border-l-[#a8323b] [&_[data-icon]]:!text-[#a8323b]",
        },
      }}
      {...props}
    />
  );
};

export { Toaster, toast };
