// Get the currently active "wrapped" year based on the current date.
export const getWrappedYear = () => {
    return computeWrappedYear(new Date());
};

export const computeWrappedYear = (date: Date): number => {
    const year = date.getFullYear();

    if (date.getMonth() === 11) {
        // If it's December (11), we allow showing wrapped for the current year
        return year;
    }

    // Otherwise, return the previous year
    return year - 1;
};
