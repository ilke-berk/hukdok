
export const validateTCIdentity = (value: string): { isValid: boolean, message: string | null } => {
    // Empty check
    if (!value) {
        return { isValid: true, message: null }; // Allow empty if not required, or handle required in form
    }

    // Must be numeric
    if (!/^\d+$/.test(value)) {
        return { isValid: false, message: "Sadece rakam girebilirsiniz." };
    }

    // Tax ID (Vergi No) Check - 10 digits
    if (value.length === 10) {
        return { isValid: true, message: null };
    }

    // TC Identity Check - 11 digits
    if (value.length === 11) {
        // First digit cannot be 0
        if (value[0] === '0') {
            return { isValid: false, message: "TC Kimlik No 0 ile başlayamaz." };
        }

        const digits = value.split('').map(Number);

        // 1, 3, 5, 7, 9. hanelerin toplamı (index 0, 2, 4, 6, 8)
        const oddSum = digits[0] + digits[2] + digits[4] + digits[6] + digits[8];

        // 2, 4, 6, 8. hanelerin toplamı (index 1, 3, 5, 7)
        const evenSum = digits[1] + digits[3] + digits[5] + digits[7];

        // 10. hane kontrolü: ((oddSum * 7) - evenSum) % 10
        const digit10 = ((oddSum * 7) - evenSum) % 10;

        if (digit10 !== digits[9]) {
            return { isValid: false, message: "Geçersiz TC Kimlik No." };
        }

        // 11. hane kontrolü: (ilk 10 hane toplamı) % 10
        const first10Sum = digits.slice(0, 10).reduce((acc, curr) => acc + curr, 0);
        const digit11 = first10Sum % 10;

        if (digit11 !== digits[10]) {
            return { isValid: false, message: "Geçersiz TC Kimlik No." };
        }

        return { isValid: true, message: null };
    }

    return { isValid: false, message: "TC No 11 haneli veya Vergi No 10 haneli olmalıdır." };
};
