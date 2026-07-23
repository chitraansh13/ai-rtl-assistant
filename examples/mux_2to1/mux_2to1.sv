module mux_2to1 (
    input  logic a,
    input  logic b,
    input  logic select,
    output logic y
);

    always_comb begin
        if (select == 1'b0)
            y = a;
        else
            y = b;
    end

endmodule