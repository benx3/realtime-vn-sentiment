import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.functions.source.SourceFunction;
import org.apache.flink.streaming.api.functions.sink.SinkFunction;
import org.apache.flink.streaming.api.datastream.DataStream;

public class LongRunningMonitoringJob {
    
    public static void main(String[] args) throws Exception {
        final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        
        // Create a source that generates monitoring data every 10 seconds
        DataStream<String> monitoringStream = env.addSource(new MonitoringSource());
        
        // Add a simple sink that logs the data
        monitoringStream.addSink(new MonitoringSink());
        
        // Execute the job
        env.execute("Vietnamese Sentiment Analysis Monitoring Job");
    }
    
    // Source that generates monitoring data
    public static class MonitoringSource implements SourceFunction<String> {
        private volatile boolean isRunning = true;
        
        @Override
        public void run(SourceContext<String> ctx) throws Exception {
            int counter = 0;
            while (isRunning) {
                counter++;
                String message = String.format("Monitor #%d - Sentiment Analysis System Active - %d", 
                    counter, System.currentTimeMillis());
                ctx.collect(message);
                Thread.sleep(10000); // 10 seconds
            }
        }
        
        @Override
        public void cancel() {
            isRunning = false;
        }
    }
    
    // Sink that logs monitoring data
    public static class MonitoringSink implements SinkFunction<String> {
        @Override
        public void invoke(String value, Context context) throws Exception {
            System.out.println("📊 " + value);
        }
    }
}