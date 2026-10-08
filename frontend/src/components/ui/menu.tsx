import * as React from "react";
import { DropdownMenu as Menu, Popover as PopoverPrimitive, Tooltip as TooltipPrimitive } from "radix-ui";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export const DropdownMenu = Menu.Root;
export const DropdownMenuTrigger = Menu.Trigger;

export function DropdownMenuContent({ className, sideOffset = 6, ...props }: React.ComponentProps<typeof Menu.Content>) {
  return (
    <Menu.Portal>
      <Menu.Content
        sideOffset={sideOffset}
        className={cn(
          "z-50 min-w-40 rounded-md border border-line bg-surface p-1 shadow-[0_12px_32px_-12px_rgb(0_0_0/0.3)] data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          className,
        )}
        {...props}
      />
    </Menu.Portal>
  );
}

export function DropdownMenuItem({
  className,
  danger,
  ...props
}: React.ComponentProps<typeof Menu.Item> & { danger?: boolean }) {
  return (
    <Menu.Item
      className={cn(
        "flex cursor-default select-none items-center gap-2 rounded-sm px-2 py-1.5 text-base outline-none data-[highlighted]:bg-sunken [&_svg]:size-4 [&_svg]:text-muted",
        danger && "text-down [&_svg]:text-down",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuRadioItem({ className, children, ...props }: React.ComponentProps<typeof Menu.RadioItem>) {
  return (
    <Menu.RadioItem
      className={cn(
        "relative flex cursor-default select-none items-center gap-2 rounded-sm py-1.5 pl-2 pr-8 text-base outline-none data-[highlighted]:bg-sunken [&_svg]:size-4 [&_svg]:text-muted",
        className,
      )}
      {...props}
    >
      {children}
      <Menu.ItemIndicator className="absolute right-2">
        <Check className="size-4 stroke-[2.5] !text-ink" />
      </Menu.ItemIndicator>
    </Menu.RadioItem>
  );
}

export const DropdownMenuRadioGroup = Menu.RadioGroup;

export function DropdownMenuSeparator() {
  return <Menu.Separator className="my-1 h-px bg-line" />;
}

export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;
export const PopoverAnchor = PopoverPrimitive.Anchor;

/** `portal={false}` keeps the content inside a parent Dialog, so its focus trap allows typing. */
export function PopoverContent({
  className,
  sideOffset = 6,
  align = "start",
  portal = true,
  ...props
}: React.ComponentProps<typeof PopoverPrimitive.Content> & { portal?: boolean }) {
  const content = (
    <PopoverPrimitive.Content
      sideOffset={sideOffset}
      align={align}
      className={cn(
        "z-50 rounded-md border border-line bg-surface shadow-[0_12px_32px_-12px_rgb(0_0_0/0.3)] outline-none data-[state=open]:animate-in data-[state=open]:fade-in-0",
        className,
      )}
      {...props}
    />
  );
  return portal ? <PopoverPrimitive.Portal>{content}</PopoverPrimitive.Portal> : content;
}

export const TooltipProvider = TooltipPrimitive.Provider;

export function Tooltip({ content, children, side = "top" }: { content: React.ReactNode; children: React.ReactNode; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          className="z-50 max-w-72 rounded-md bg-ink px-2.5 py-1.5 text-sm text-paper shadow-lg data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0"
        >
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
