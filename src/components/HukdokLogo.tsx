import logoBrand from "@/assets/logo_brand.png";

export default function HukdokLogo({ className }: { className?: string }) {
    return (
        <img
            src={logoBrand}
            alt="Hukdok Logo"
            className={`w-20 h-auto ${className}`}
        />
    );
}
