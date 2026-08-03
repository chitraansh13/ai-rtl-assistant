module alu_4bit (
    input  logic [3:0] a,
    input  logic [3:0] b,
    input  logic [1:0] opcode,
    output logic [3:0] result,
    output logic       carry,
    output logic       zero
);

    always_comb begin
        // Default values
        result = 4'b0000;
        carry  = 1'b0;

        case (opcode)
            2'b00: begin
                // ADD
                {carry, result} = a + b;
            end

            2'b01: begin
                // SUBTRACT
                result = a - b;
            end

            2'b10: begin
                // AND
                result = a & b;
            end

            2'b11: begin
                // OR
                result = a | b;
            end

            default: begin
                result = 4'b0000;
                carry  = 1'b0;
            end
        endcase

        // Zero flag becomes 1 when result is zero
        zero = (result == 4'b0000);
    end

endmodule
