import React from "react";

export const ChartSynchronizerContext = React.createContext<
    | {
          yMax: number | undefined;
          onYMaxChange: (yMax: number) => void;
          synchronized: true;
      }
    | {
          yMax?: undefined;
          onYMaxChange?: undefined;
          synchronized: false;
      }
>({ synchronized: false });
