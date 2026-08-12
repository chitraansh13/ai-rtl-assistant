module fifo_sync #(
    parameter int DATA_WIDTH = 8,
    parameter int DEPTH = 16,
    parameter int ADDR_WIDTH = $clog2(DEPTH)
) (
    input  logic                  clk,
    input  logic                  rst,
    input  logic                  wr_en,
    input  logic                  rd_en,
    input  logic [DATA_WIDTH-1:0] data_in,
    output logic [DATA_WIDTH-1:0] data_out,
    output logic                  full,
    output logic                  empty,
    output logic [ADDR_WIDTH:0]   count
);

    logic [DATA_WIDTH-1:0] mem [0:DEPTH-1];
    logic [ADDR_WIDTH-1:0] wr_ptr;
    logic [ADDR_WIDTH-1:0] rd_ptr;

    logic do_write;
    logic do_read;

    assign full     = (count == DEPTH);
    assign empty    = (count == 0);
    assign do_write = wr_en && !full;
    assign do_read  = rd_en && !empty;

    always_ff @(posedge clk) begin
        if (rst) begin
            wr_ptr   <= '0;
            rd_ptr   <= '0;
            count    <= '0;
            data_out <= '0;
        end else begin
            case ({do_write, do_read})
                2'b10: begin
                    mem[wr_ptr] <= data_in;
                    if (wr_ptr == ADDR_WIDTH'(DEPTH - 1))
                        wr_ptr <= '0;
                    else
                        wr_ptr <= wr_ptr + 1'b1;
                    count <= count + 1'b1;
                end

                2'b01: begin
                    data_out <= mem[rd_ptr];
                    if (rd_ptr == ADDR_WIDTH'(DEPTH - 1))
                        rd_ptr <= '0;
                    else
                        rd_ptr <= rd_ptr + 1'b1;
                    count <= count - 1'b1;
                end

                2'b11: begin
                    // A read returns the oldest stored item; count is unchanged.
                    mem[wr_ptr] <= data_in;
                    data_out    <= mem[rd_ptr];
                    if (wr_ptr == ADDR_WIDTH'(DEPTH - 1))
                        wr_ptr <= '0;
                    else
                        wr_ptr <= wr_ptr + 1'b1;
                    if (rd_ptr == ADDR_WIDTH'(DEPTH - 1))
                        rd_ptr <= '0;
                    else
                        rd_ptr <= rd_ptr + 1'b1;
                end

                default: ;
            endcase
        end
    end

endmodule