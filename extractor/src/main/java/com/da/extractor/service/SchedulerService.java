package com.da.extractor.service;

import com.da.extractor.entity.SchedulerConfig;
import com.da.extractor.entity.training.TrainConfig;
import com.da.extractor.pipeline.DataPipelineFactory;
import com.da.extractor.pipeline.PipeMetadata;
import com.da.extractor.repository.anomaly_detection.TrainingConfigRepository;
import com.da.extractor.repository.scheduler.SchedulerConfigRepository;
import org.springframework.scheduling.TaskScheduler;
import org.springframework.scheduling.Trigger;
import org.springframework.scheduling.support.CronTrigger;
import org.springframework.stereotype.Service;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.ScheduledFuture;

@Service
public class SchedulerService {

    private static final Logger log = LoggerFactory.getLogger(SchedulerService.class);

    private final TaskScheduler taskScheduler;

    private final Map<String, ScheduledFuture<?>> scheduledTasks = new HashMap<>();
    private final SchedulerConfigRepository schedulerConfigRepository;
    private final TrainingConfigRepository trainingConfigRepository;

    private final DataPipelineFactory dataPipelineFactory;

    private static final DateTimeFormatter ISO = DateTimeFormatter.ISO_INSTANT;

    public SchedulerService(TaskScheduler taskScheduler,
                            SchedulerConfigRepository schedulerConfigRepository,
                            TrainingConfigRepository trainingConfigRepository,
                            DataPipelineFactory dataPipelineFactory) {
        this.taskScheduler = taskScheduler;
        this.schedulerConfigRepository = schedulerConfigRepository;
        this.trainingConfigRepository = trainingConfigRepository;
        this.dataPipelineFactory = dataPipelineFactory;
    }

    public void createStreamingTask(SchedulerConfig config, PipeMetadata pipeMetadata) {

        long seconds = config.getLastRun().toInstant().getEpochSecond();
        String sixValuesCron = normalizeCron(config.getFrequency(), seconds);
        CronTrigger cronTrigger = new CronTrigger(sixValuesCron);
        Runnable task = () -> {
            try {
                // Gracefully handle missing TrainConfig instead of crashing
                var trainConfigOpt = trainingConfigRepository.findByKbId(config.getKbId());
                if (trainConfigOpt.isEmpty()) {
                    log.warn("TrainConfig not found for KB ID: {}. Skipping detection cycle.", config.getKbId());
                    return;
                }
                TrainConfig trainConfig = trainConfigOpt.get();

                if(trainConfig.isTrained()){
                    Instant to  = Instant.now();
                    Instant from = to.minusSeconds(config.getWindow());
                    String elasticQuery = config.getQuery()
                            .replace("$from", ISO.format(from))
                            .replace("$to",   ISO.format(to));

                    var pipeline = dataPipelineFactory.createPipeline(pipeMetadata);
                    pipeline.process(elasticQuery);

                    config.setLastRun(Date.from(Instant.now()));
                    schedulerConfigRepository.save(config);
                    log.info("Scheduled task executed for KB ID: {} | from: {} | to: {}",
                            config.getKbId(), ISO.format(from), ISO.format(to));
                }

            } catch (Exception ex) {
                log.error("Error en scheduleStreamingTask({}): {}", config.getKbId(), ex.getMessage(), ex);
            }
        };
        // Trigger compuesto usando Instant (API moderna)
        Trigger composedTrigger = context -> {
            Instant last = context.lastScheduledExecution(); // puede ser null primera vez
            if (last == null) {
                if (config.getFrom() != null) {
                    Instant startInstant = config.getFrom().toInstant();
                    if (startInstant.isAfter(Instant.now())) {
                        return startInstant; // Primera ejecución en startAt futuro
                    }
                }
                // Ejecutar inmediatamente o según cron siguiente
                return cronTrigger.nextExecution(context);
            }
            return cronTrigger.nextExecution(context);
        };
        cancelTask(config.getKbId());
        ScheduledFuture<?> future = taskScheduler.schedule(task, composedTrigger);
        scheduledTasks.put(config.getKbId(), future);
        log.info("Scheduled task saved for KB ID: {} with frequency: {}",
                config.getKbId(), config.getFrequency());
    }

    private String normalizeCron(String cron, long seconds){
        String[] parts = cron.trim().split("\\s+");
        return (parts.length == 5) ? seconds + " " + cron : cron;
    }

    public void cancelTask(String id) {
        ScheduledFuture<?> f = scheduledTasks.remove(id);
        if (f != null) {
            f.cancel(false);
        }
    }
}