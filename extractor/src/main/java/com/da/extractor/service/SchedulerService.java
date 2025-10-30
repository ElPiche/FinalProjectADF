package com.da.extractor.service;

import com.da.extractor.entity.serie.Mode;
import com.da.extractor.pipeline.DataPipelineFactory;
import com.da.extractor.pipeline.PipeMetadata;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.Trigger;
import org.springframework.scheduling.support.CronTrigger;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.*;
import java.util.concurrent.ScheduledFuture;

@Service
public class SchedulerService {

    private final TaskScheduler taskScheduler;

    private Map<String, ScheduledFuture<?>> scheduledTasks = new HashMap<>();

    private final DataPipelineFactory dataPipelineFactory;

    private static final DateTimeFormatter ISO = DateTimeFormatter.ISO_INSTANT;

    public SchedulerService(TaskScheduler taskScheduler, DataPipelineFactory dataPipelineFactory) {
        this.taskScheduler = taskScheduler;
        this.dataPipelineFactory = dataPipelineFactory;
    }

    public void createTask(String text, long rateMillis) {
        Runnable task = () -> System.out.println("Scheduled Task: " + text);

        ScheduledFuture<?> scheduledFuture = taskScheduler.scheduleAtFixedRate(
                task, Duration.ofMillis(rateMillis)
        );

        scheduledTasks.put(UUID.randomUUID().toString(), scheduledFuture);
    }

    public void createStreamingTask(String query, int window, String frequency, String id, List<String> observedValues) throws Exception {

        String cron = normalizeCron(frequency);

        Trigger trigger = new CronTrigger(cron);// TimeZone.getTimeZone(ZONE)

        Runnable task = () -> {
            try {
                // Ventana: últimos N segundos
                Instant to  = Instant.now();
                Instant from = to.minusSeconds(window);

                String elasticQuery = query
                        .replace("$from", ISO.format(from))
                        .replace("$to",   ISO.format(to));

                var pipeline = dataPipelineFactory.createPipeline(new PipeMetadata(
                        id,
                        observedValues,
                        Mode.DETECTION
                ));

                pipeline.process(elasticQuery);

            } catch (Exception ex) {
                System.err.println("Error en scheduleStreamingTask(" + id + "): " + ex.getMessage());
                ex.printStackTrace();
            }
        };

        cancelTask(id);

        ScheduledFuture<?> future = taskScheduler.schedule(task, trigger);

        scheduledTasks.put(id, future);

    }

    //normalizador de cron
    private String normalizeCron(String cron){
        String[] parts = cron.trim().split("\\s+");
        return (parts.length == 5) ? "0 " + cron : cron;
    }

    //Detención de tareas por id
    public boolean cancelTask(String id) {
        ScheduledFuture<?> f = scheduledTasks.remove(id);
        return f != null && f.cancel(false);
    }
}
